from pathlib import Path
import os
import pytest
from wikidebia_checkpoint_store import StoreError, inventory

def _write(root, name, content):
    p = root / ".state/resume-checkpoints/debate/work" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p

def test_dry_run_and_apply_preserve_contents(tmp_path):
    a = _write(tmp_path, "a.zip", b"same")
    b = _write(tmp_path, "b.zip", b"same")
    c = _write(tmp_path, "c.zip", b"other")
    result = inventory(tmp_path)
    assert result["potential_duplicate_bytes"] == 4
    assert not (tmp_path / ".state/checkpoint-objects").exists()
    result = inventory(tmp_path, apply=True)
    assert result["linked_files"] == 2
    assert a.read_bytes() == b.read_bytes() == b"same"
    assert c.read_bytes() == b"other"
    assert a.stat().st_ino == b.stat().st_ino
    assert inventory(tmp_path, apply=True)["linked_files"] == 0

def test_prune_only_unreferenced_objects(tmp_path):
    a = _write(tmp_path, "a.zip", b"same")
    b = _write(tmp_path, "b.zip", b"same")
    inventory(tmp_path, apply=True)
    assert inventory(tmp_path, apply=True, prune=True)["pruned_objects"] == 0
    a.unlink()
    b.unlink()
    assert inventory(tmp_path, apply=True, prune=True)["pruned_objects"] == 1

def test_symlink_is_rejected(tmp_path):
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"secret")
    p = tmp_path / ".state/resume-checkpoints/debate/work/evil.zip"
    p.parent.mkdir(parents=True)
    p.symlink_to(outside)
    with pytest.raises(StoreError, match="non sûr"):
        inventory(tmp_path)

def test_tampered_object_blocks_apply(tmp_path):
    _write(tmp_path, "a.zip", b"same")
    _write(tmp_path, "b.zip", b"same")
    inventory(tmp_path, apply=True)
    obj = next((tmp_path / ".state/checkpoint-objects").glob("*/*"))
    # Replacing the object, rather than mutating hardlinked checkpoint data.
    replacement = obj.with_suffix(".tmp")
    replacement.write_bytes(b"wrong")
    os.replace(replacement, obj)
    with pytest.raises(StoreError, match="altéré"):
        inventory(tmp_path, apply=True)
