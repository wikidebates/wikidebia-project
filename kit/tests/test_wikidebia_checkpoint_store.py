from pathlib import Path
import pytest
import os
import errno
import wikidebia_checkpoint_store as store
from wikidebia_checkpoint_store import StoreError, inventory

def _write(root, name, content):
    p = root / ".state/resume-checkpoints/debate/work" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p

def test_dry_run_and_apply_preserve_contents(tmp_path, monkeypatch):
    def fake_reflink(dst, request, src):
        os.lseek(src, 0, os.SEEK_SET)
        while True:
            data = os.read(src, 4096)
            if not data:
                break
            os.write(dst, data)
    monkeypatch.setattr(store.fcntl, 'ioctl', fake_reflink)
    a = _write(tmp_path, "a.zip", b"same")
    b = _write(tmp_path, "b.zip", b"same")
    c = _write(tmp_path, "c.zip", b"other")
    result = inventory(tmp_path)
    assert result["potential_duplicate_bytes"] == 4
    assert not (tmp_path / ".state/checkpoint-objects").exists()
    result = inventory(tmp_path, apply=True)
    assert result["linked_files"] == 1
    assert a.read_bytes() == b.read_bytes() == b"same"
    assert c.read_bytes() == b"other"
    assert a.stat().st_ino != b.stat().st_ino
    a.write_bytes(b"changed")
    assert b.read_bytes() == b"same"
    assert inventory(tmp_path, apply=True)["linked_files"] == 0

def test_prune_is_disabled(tmp_path):
    _write(tmp_path, "a.zip", b"same")
    _write(tmp_path, "b.zip", b"same")
    with pytest.raises(StoreError, match="prune"):
        inventory(tmp_path, apply=True, prune=True)

def test_symlink_is_rejected(tmp_path):
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"secret")
    p = tmp_path / ".state/resume-checkpoints/debate/work/evil.zip"
    p.parent.mkdir(parents=True)
    p.symlink_to(outside)
    with pytest.raises(StoreError, match="non sûr"):
        inventory(tmp_path)

def test_parent_symlink_is_rejected(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "a.zip").write_bytes(b"same")
    (tmp_path / ".state").mkdir()
    (tmp_path / ".state/resume-checkpoints").symlink_to(external, target_is_directory=True)
    with pytest.raises(StoreError, match="symbolique"):
        inventory(tmp_path)


def test_unsupported_reflink_preserves_originals(tmp_path, monkeypatch):
    a = _write(tmp_path, "a.zip", b"same")
    b = _write(tmp_path, "b.zip", b"same")
    def unsupported(*args):
        raise OSError(errno.EOPNOTSUPP, "unsupported")
    monkeypatch.setattr(store.fcntl, "ioctl", unsupported)
    with pytest.raises(StoreError, match="Reflink"):
        inventory(tmp_path, apply=True)
    assert a.read_bytes() == b.read_bytes() == b"same"
    assert a.stat().st_ino != b.stat().st_ino


def test_legacy_hardlinks_are_reported_and_repaired_atomically(tmp_path):
    a = _write(tmp_path, "a.zip", b"legacy shared checkpoint")
    b = a.with_name("b.zip")
    os.link(a, b)
    external = tmp_path / ".state/checkpoint-objects/legacy.zip"
    external.parent.mkdir(parents=True)
    os.link(a, external)

    report = inventory(tmp_path)
    assert report["hardlinked_files"] == 2
    assert report["hardlinked_inode_groups"] == 1
    assert report["repaired_hardlinks"] == 0

    repaired = inventory(tmp_path, repair_hardlinks=True)

    assert repaired["repaired_hardlinks"] == 2
    assert len({a.stat().st_ino, b.stat().st_ino, external.stat().st_ino}) == 3
    a.write_bytes(b"changed independently")
    assert b.read_bytes() == external.read_bytes() == b"legacy shared checkpoint"
    assert inventory(tmp_path)["hardlinked_files"] == 0


def test_repair_and_reflink_apply_are_mutually_exclusive(tmp_path):
    with pytest.raises(StoreError, match="incompatibles"):
        inventory(tmp_path, apply=True, repair_hardlinks=True)
