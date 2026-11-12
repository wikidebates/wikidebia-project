from pathlib import Path
import pytest
import os
import errno
import json
import sys
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
    unsigned_plan = dict(result["mutation_plan"])
    assert unsigned_plan.pop("plan_sha256") == store._object_sha(unsigned_plan)
    assert not (tmp_path / ".state/checkpoint-objects").exists()
    result = inventory(tmp_path, apply=True, confirm_plan_sha256=result["plan_sha256"])
    assert result["linked_files"] == 1
    assert result["mutation_receipt"]["mutation_count"] == 1
    assert (tmp_path / result["mutation_receipt_path"]).is_file()
    assert a.read_bytes() == b.read_bytes() == b"same"
    assert c.read_bytes() == b"other"
    assert a.stat().st_ino != b.stat().st_ino
    a.write_bytes(b"changed")
    assert b.read_bytes() == b"same"
    next_plan = inventory(tmp_path)
    assert inventory(
        tmp_path, apply=True, confirm_plan_sha256=next_plan["plan_sha256"]
    )["linked_files"] == 0

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
    plan = inventory(tmp_path)
    with pytest.raises(StoreError, match="Reflink"):
        inventory(tmp_path, apply=True, confirm_plan_sha256=plan["plan_sha256"])
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

    repaired = inventory(
        tmp_path, repair_hardlinks=True, confirm_plan_sha256=report["plan_sha256"]
    )

    assert repaired["repaired_hardlinks"] == 2
    assert len({a.stat().st_ino, b.stat().st_ino, external.stat().st_ino}) == 3
    a.write_bytes(b"changed independently")
    assert b.read_bytes() == external.read_bytes() == b"legacy shared checkpoint"
    assert inventory(tmp_path)["hardlinked_files"] == 0
    receipt_path = tmp_path / repaired["mutation_receipt_path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    unsigned = dict(receipt)
    assert unsigned.pop("receipt_sha256") == store._object_sha(unsigned)
    assert receipt["post_hardlinked_files"] == 0
    assert receipt["mutation_plan"]["plan_sha256"] == repaired["plan_sha256"]


def test_repair_and_reflink_apply_are_mutually_exclusive(tmp_path):
    with pytest.raises(StoreError, match="incompatibles"):
        inventory(tmp_path, apply=True, repair_hardlinks=True)


def test_reflink_apply_refuses_legacy_hardlinks_before_mutation(tmp_path):
    a = _write(tmp_path, "a.zip", b"same")
    b = a.with_name("b.zip")
    os.link(a, b)
    plan = inventory(tmp_path)
    inode = a.stat().st_ino
    with pytest.raises(StoreError, match="repair-hardlinks"):
        inventory(tmp_path, apply=True, confirm_plan_sha256=plan["plan_sha256"])
    assert a.stat().st_ino == b.stat().st_ino == inode
    assert not (tmp_path / ".state/checkpoint-maintenance").exists()


def test_mutation_requires_exact_current_plan_confirmation(tmp_path):
    a = _write(tmp_path, "a.zip", b"same")
    b = _write(tmp_path, "b.zip", b"same")
    plan = inventory(tmp_path)
    with pytest.raises(StoreError, match="Confirmation du plan"):
        inventory(tmp_path, apply=True)
    with pytest.raises(StoreError, match="Confirmation du plan"):
        inventory(tmp_path, apply=True, confirm_plan_sha256="0" * 64)
    b.write_bytes(b"changed")
    with pytest.raises(StoreError, match="Confirmation du plan"):
        inventory(tmp_path, apply=True, confirm_plan_sha256=plan["plan_sha256"])
    assert a.read_bytes() == b"same"
    assert b.read_bytes() == b"changed"
    assert not (tmp_path / ".state/checkpoint-maintenance").exists()


def test_backup_scope_deduplicates_only_immutable_backup_roots(tmp_path, monkeypatch):
    release_backup = (
        tmp_path / ".state/release-rebuild-backups/debate/EDIT-TEST-001/run/release-copy/a.wiki"
    )
    workspace_backup = (
        tmp_path / ".state/editorial-workspaces/debate/EDIT-TEST-001/backups/run/a.wiki"
    )
    active = tmp_path / ".state/editorial-workspaces/debate/EDIT-TEST-001/release-copy/a.wiki"
    for path in (release_backup, workspace_backup, active):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"immutable duplicate")

    report = inventory(tmp_path, scope="backups")
    assert report["scope"] == "backups"
    assert report["files"] == 2
    assert report["potential_duplicate_bytes"] == len(b"immutable duplicate")
    assert all(
        "/release-copy/a.wiki" not in row["path"]
        or "release-rebuild-backups" in row["path"]
        for row in report["mutation_plan"]["files"]
    )

    def fake_reflink(dst, request, src):
        os.lseek(src, 0, os.SEEK_SET)
        os.write(dst, os.read(src, 4096))

    monkeypatch.setattr(store.fcntl, "ioctl", fake_reflink)
    applied = inventory(
        tmp_path,
        scope="backups",
        apply=True,
        confirm_plan_sha256=report["plan_sha256"],
    )
    assert applied["linked_files"] == 1
    assert applied["mutation_receipt"]["scope"] == "backups"
    assert release_backup.read_bytes() == workspace_backup.read_bytes() == b"immutable duplicate"
    assert active.read_bytes() == b"immutable duplicate"
    assert active.stat().st_ino not in {release_backup.stat().st_ino, workspace_backup.stat().st_ino}


def test_unknown_storage_scope_is_rejected(tmp_path):
    with pytest.raises(StoreError, match="Périmètre inconnu"):
        inventory(tmp_path, scope="everything")


def test_backup_scope_rejects_symbolic_workspace_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    state = tmp_path / ".state"
    state.mkdir()
    (state / "editorial-workspaces").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StoreError, match="symbolique"):
        inventory(tmp_path, scope="backups")


def test_cli_output_keeps_large_plan_out_of_console(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "a.zip", b"same")
    output = tmp_path / ".state/dedup-plan.json"
    monkeypatch.setattr(sys, "argv", [
        "wikidebia_checkpoint_store.py", "--project-root", str(tmp_path),
        "--output", str(output),
    ])
    assert store.main() == 0
    summary = json.loads(capsys.readouterr().out)
    full = json.loads(output.read_text(encoding="utf-8"))
    assert summary["output"] == ".state/dedup-plan.json"
    assert summary["plan_sha256"] == full["plan_sha256"]
    assert "mutation_plan" not in summary
    assert full["mutation_plan"]["files"][0]["path"].endswith("a.zip")
