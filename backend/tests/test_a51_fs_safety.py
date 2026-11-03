"""
ZWM v1.1.0 Block A5.1 — repository data cannot be modified or deleted by tests.

Every probe below targets a path that does NOT exist inside a protected repository
directory, so even if a guard were missing nothing real could be lost; the tests
assert that the guard raises before the operation runs, and that the repository's
protected trees are byte-for-byte unchanged afterwards.
"""
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.services import fs_safety
from app.services.fs_safety import UnsafeFilesystemOperation

REPO = fs_safety.BACKEND_ROOT
PROTECTED_DIRS = [REPO / "uploads", REPO / "models", REPO / "worker"]


def _tree_digest():
    """(relative path, size, sha256) for every file under the protected directories."""
    out = []
    for root in PROTECTED_DIRS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                out.append((str(p.relative_to(REPO)), p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


@pytest.fixture(scope="module")
def repo_digest():
    before = _tree_digest()
    yield before
    assert _tree_digest() == before, "protected repository data changed during A5.1 safety tests"


def _probe(*parts):
    return REPO.joinpath(*parts, f"__a51_probe_{uuid.uuid4().hex}")


# ---------------------------------------------------------------------------
# Session configuration (fail closed)
# ---------------------------------------------------------------------------

class TestIsolationIsActive:
    def test_audit_hook_installed_and_root_valid(self):
        assert fs_safety.audit_hook_installed()
        root = fs_safety.validate_test_root(os.environ[fs_safety.TEST_ROOT_ENV])
        assert not fs_safety.is_within(root, REPO)

    def test_every_data_setting_is_inside_the_disposable_root(self):
        fs_safety.validate_settings_paths(settings, os.environ[fs_safety.TEST_ROOT_ENV])
        for name in fs_safety.DATA_PATH_SETTINGS:
            assert not fs_safety.is_within(getattr(settings, name), REPO), name

    @pytest.mark.parametrize("method", ["train", "val", "predict", "__call__", "track", "export"])
    def test_real_yolo_operations_are_blocked(self, method):
        from conftest import RealTrainingBlocked
        from ultralytics.engine.model import Model
        with pytest.raises(RealTrainingBlocked):
            getattr(Model, method)(object())

    def test_weight_downloads_are_blocked(self):
        from conftest import RealTrainingBlocked
        import ultralytics.utils.downloads as d
        with pytest.raises(RealTrainingBlocked):
            d.attempt_download_asset(f"definitely_missing_{uuid.uuid4().hex}.pt")
        with pytest.raises(RealTrainingBlocked):
            d.safe_download("https://example.invalid/w.pt")

    def test_database_is_a_test_database(self):
        assert "test" in settings.DATABASE_URL.rsplit("/", 1)[-1].lower()

    @pytest.mark.parametrize("bad", ["", "repo", "repo_child", "not_temp", "missing"])
    def test_invalid_roots_are_rejected(self, bad, tmp_path):
        value = {"": "", "repo": str(REPO), "repo_child": str(REPO / "uploads"),
                 "not_temp": str(Path(REPO.anchor) / "zwm_not_temp_root_a51"),
                 "missing": str(Path(tempfile.gettempdir()) / f"missing_{uuid.uuid4().hex}")}[bad]
        with pytest.raises(UnsafeFilesystemOperation):
            fs_safety.validate_test_root(value)

    def test_settings_outside_root_are_rejected(self, tmp_path, monkeypatch):
        root = tmp_path / "root"
        root.mkdir()
        monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(REPO / "uploads"))
        with pytest.raises(UnsafeFilesystemOperation, match="UPLOAD_FOLDER"):
            fs_safety.validate_settings_paths(settings, root)


# ---------------------------------------------------------------------------
# Runtime guard: every destructive primitive is blocked on protected paths
# ---------------------------------------------------------------------------

class TestProtectedPathsAreBlocked:
    @pytest.mark.parametrize("area", ["uploads", "models", "worker"])
    def test_create_and_overwrite_blocked(self, repo_digest, area):
        target = _probe(area)
        for write in (lambda: open(target, "w").close(), lambda: target.write_bytes(b"x"),
                      lambda: open(target, "ab").close(), lambda: os.open(target, os.O_CREAT | os.O_WRONLY)):
            with pytest.raises(UnsafeFilesystemOperation):
                write()
        assert not target.exists()

    def test_existing_weights_cannot_be_overwritten_or_truncated(self, repo_digest):
        weights = REPO / "models" / "best.pt"
        if not weights.exists():
            pytest.skip("no repository serving placeholder present")
        # precondition: prove the guard is live on a harmless probe before touching a real file
        assert fs_safety.audit_hook_installed()
        with pytest.raises(UnsafeFilesystemOperation):
            open(_probe("models"), "wb")
        with pytest.raises(UnsafeFilesystemOperation):
            open(weights, "wb")
        with pytest.raises(UnsafeFilesystemOperation):
            os.truncate(weights, 0)

    @pytest.mark.parametrize("area", ["uploads/dataset", "uploads/permanent", "models", "worker"])
    def test_delete_primitives_blocked(self, repo_digest, area):
        target = _probe(*area.split("/"))                   # does not exist: nothing at stake
        for delete in (lambda: os.remove(target), lambda: target.unlink(), lambda: os.rmdir(target),
                       lambda: shutil.rmtree(target)):
            with pytest.raises(UnsafeFilesystemOperation):
                delete()

    def test_move_rename_copy_into_or_out_of_repo_blocked(self, repo_digest, tmp_path):
        outside = tmp_path / "f.txt"
        outside.write_text("x")
        inside = _probe("uploads", "dataset")
        for op in (lambda: os.rename(outside, inside), lambda: os.replace(outside, inside),
                   lambda: shutil.move(str(outside), str(inside)), lambda: shutil.copyfile(outside, inside),
                   lambda: os.rename(_probe("uploads"), tmp_path / "stolen")):
            with pytest.raises(UnsafeFilesystemOperation):
                op()
        assert outside.exists() and not inside.exists()

    def test_new_directories_blocked_but_existing_ones_tolerated(self, repo_digest):
        with pytest.raises(UnsafeFilesystemOperation):
            os.makedirs(_probe("uploads", "dataset"))
        os.makedirs(REPO / "uploads", exist_ok=True)               # already exists: no change, allowed

    def test_reads_are_still_allowed(self, repo_digest):
        for f in (REPO / "models").glob("*_metadata.json"):
            f.read_bytes()
            break

    def test_disposable_root_is_writable(self):
        p = Path(settings.UPLOAD_FOLDER) / "dataset" / "ok" / "f.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fine")
        shutil.rmtree(p.parent)
        assert not p.parent.exists()


# ---------------------------------------------------------------------------
# Application code: no hardcoded fallbacks, confined to the configured root
# ---------------------------------------------------------------------------

class TestLifecycleCleanupIsConfined:
    def test_assert_within(self, tmp_path):
        root = tmp_path / "uploads"
        (root / "dataset").mkdir(parents=True)
        assert fs_safety.assert_within(root / "dataset", root)
        for bad in (tmp_path / "other", root / ".." / "escape", REPO / "uploads" / "dataset"):
            with pytest.raises(UnsafeFilesystemOperation):
                fs_safety.assert_within(bad, root)

    def test_sync_only_scans_configured_root(self, repo_digest, monkeypatch, tmp_path):
        from app.services import lifecycle_service as ls

        class _NoCategories:
            def query(self, *_):
                return self

            def all(self):
                return []

        upload = tmp_path / "uploads"
        orphan = upload / "dataset" / "orphan_cat"
        keep = upload / "dataset" / "general"
        for d in (orphan, keep):
            d.mkdir(parents=True)
            (d / "x.txt").write_text("1")
        monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(upload))
        listed = []
        real_listdir = os.listdir
        monkeypatch.setattr(ls.os, "listdir", lambda p: listed.append(os.path.abspath(p)) or real_listdir(p))
        ls.sync_dataset_folders_with_db(_NoCategories())
        assert listed == [os.path.abspath(upload / "dataset")]          # no cwd / repository roots
        assert not orphan.exists() and keep.exists()

    def test_delete_category_folder_never_touches_repo(self, repo_digest, monkeypatch, tmp_path):
        from app.services import lifecycle_service as ls
        repo_dataset = REPO / "uploads" / "dataset"
        existing = sorted(p.name for p in repo_dataset.iterdir()) if repo_dataset.exists() else []
        monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
        (tmp_path / "uploads" / "dataset" / "plastic").mkdir(parents=True)
        for name in existing + ["plastic"]:
            ls.delete_dataset_category_folder(name)                     # same names as repository folders
        assert not (tmp_path / "uploads" / "dataset" / "plastic").exists()
        if repo_dataset.exists():
            assert sorted(p.name for p in repo_dataset.iterdir()) == existing

    def test_safe_delete_refuses_paths_outside_uploads(self, repo_digest, monkeypatch, tmp_path):
        from app.services import lifecycle_service as ls
        monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
        outside = tmp_path / "elsewhere.jpg"
        outside.write_bytes(b"keep")
        ls._safe_delete(str(outside))
        assert outside.exists()
        inside = tmp_path / "uploads" / "temporary" / "a.jpg"
        inside.parent.mkdir(parents=True)
        inside.write_bytes(b"go")
        ls._safe_delete(str(inside))
        assert not inside.exists()

    def test_no_hardcoded_repository_roots_remain(self):
        src = (REPO / "app" / "services" / "lifecycle_service.py").read_text(encoding="utf-8")
        assert 'os.path.join("uploads", "dataset")' not in src
        assert 'os.getcwd(), "uploads"' not in src
        assert '"..", "..", "uploads"' not in src

    def test_training_worker_roots_are_redirected_by_its_tests(self):
        src = (REPO / "tests" / "test_training_worker.py").read_text(encoding="utf-8")
        assert "DATASETS_ROOT.parent.parent" not in src
        assert 'monkeypatch.setattr(training_worker, "DATASETS_ROOT"' in src
