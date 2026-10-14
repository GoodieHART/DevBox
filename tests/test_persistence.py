"""Direct unit tests for persistence and backup/restore behavior.

runtime.persistence_utils and runtime.backup_utils are dependency-free,
so these tests import and execute them instead of using AST inspection.
"""

import inspect
import subprocess
import tarfile

from runtime import backup_utils
from runtime.persistence_utils import setup_persistence


def test_missing_home_preserves_volume_dir(tmp_path):
    home = tmp_path / "home"
    store = tmp_path / "store"
    vol_item = store / ".config" / "opencode"
    vol_item.mkdir(parents=True)
    (vol_item / "opencode.json").write_text('{"user": true}', encoding="utf-8")
    setup_persistence(
        [".config/opencode"],
        persistent_storage_dir=str(store),
        home_base=str(home),
    )
    assert (vol_item / "opencode.json").read_text(encoding="utf-8") == '{"user": true}'
    assert (home / ".config" / "opencode").is_symlink()


def test_genuine_type_mismatch_still_reconciles(tmp_path):
    home = tmp_path / "home"
    store = tmp_path / "store"
    (home / ".config" / "opencode").mkdir(parents=True)
    stale = store / ".config" / "opencode"
    stale.parent.mkdir(parents=True)
    stale.write_text("", encoding="utf-8")
    setup_persistence(
        [".config/opencode"],
        persistent_storage_dir=str(store),
        home_base=str(home),
    )
    assert stale.is_dir()


def test_restore_roundtrip(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "note.txt").write_text("roundtrip", encoding="utf-8")
    backup = tmp_path / "backup.tar.gz"
    assert backup_utils.create_backup(str(home), str(backup)) == str(backup)
    (home / "note.txt").unlink()
    backup_utils.restore_backup(str(backup), str(home), str(home))
    assert (home / "note.txt").read_text(encoding="utf-8") == "roundtrip"


def test_restore_skips_corrupt_backup(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    sentinel = home / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    corrupt = tmp_path / "corrupt.tar.gz"
    corrupt.write_bytes(b"not a gzip file")
    backup_utils.restore_backup(str(corrupt), str(home), str(home))
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_restore_defaults_target_root():
    params = inspect.signature(backup_utils.restore_backup).parameters
    assert params["restore_dir"].default == "/root"
    assert params["wipe_dir"].default == "/root"


def test_backup_excludes_image_managed_opencode(tmp_path):
    home = tmp_path / "home"
    (home / ".opencode" / "bin").mkdir(parents=True)
    (home / ".opencode" / "bin" / "opencode").write_text("binary", encoding="utf-8")
    (home / "note.txt").write_text("keep", encoding="utf-8")
    backup = tmp_path / "backup.tar.gz"
    backup_utils.create_backup(str(home), str(backup))
    with tarfile.open(backup, "r:gz") as archive:
        names = archive.getnames()
    assert not any(".opencode" in name for name in names)
    assert any(name.endswith("note.txt") for name in names)
    result = subprocess.run(
        ["tar", "-tzf", str(backup)], capture_output=True, check=False
    )
    assert result.returncode == 0
