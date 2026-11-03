"""
Filesystem safety guard (ZWM v1.1.0, Block A5.1).

Two layers:

1. ``assert_within(path, root)`` — used by application code before destructive
   operations (rmtree / remove / move) so they can only act inside the configured
   data root (e.g. settings.UPLOAD_FOLDER). There are no hardcoded repository
   fallbacks: a path outside the configured root is refused.

2. Test isolation. When ``ZWM_TEST_FS_ROOT`` is set (tests/conftest.py does this),
   every configured data path must live inside that disposable root, and
   ``install_test_audit_hook()`` blocks — fail closed — any write, delete, rename,
   truncate or chmod that targets the repository's protected data directories
   (uploads, models, worker, bundled weights), whatever code path performs it.
"""
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT_ENV = "ZWM_TEST_FS_ROOT"

# Repository data that tests must never modify.
PROTECTED_REPO_PATHS = tuple(
    (BACKEND_ROOT / p).resolve()
    for p in ("uploads", "models", "worker", "yolov8n.pt", "yolov8n-seg.pt", "runs")
)

# Settings that name data locations; under tests all of them must be inside the test root.
DATA_PATH_SETTINGS = (
    "UPLOAD_FOLDER", "YOLO_MODEL_PATH", "TRAINING_DATASETS_DIR", "CANDIDATE_MODELS_DIR",
    "EVALUATION_DIR", "DEPLOYED_MODELS_DIR",
)


class UnsafeFilesystemOperation(PermissionError):
    """Raised when a destructive operation targets a path outside its permitted root."""


def _resolve(path) -> Path:
    return Path(os.path.abspath(os.fspath(path))).resolve()


def is_within(path, root) -> bool:
    p, r = _resolve(path), _resolve(root)
    return p == r or r in p.parents


def assert_within(path, root, action: str = "modify") -> Path:
    """Refuse ``action`` on ``path`` unless it is ``root`` or below it (symlinks resolved)."""
    if not root:
        raise UnsafeFilesystemOperation(f"refusing to {action} {path}: no permitted root configured")
    if not is_within(path, root):
        raise UnsafeFilesystemOperation(f"refusing to {action} {path}: outside permitted root {root}")
    if test_root() is not None and is_protected_repo_path(path):
        raise UnsafeFilesystemOperation(f"refusing to {action} protected repository path {path} under tests")
    return _resolve(path)


def is_protected_repo_path(path) -> bool:
    p = _resolve(path)
    if "__pycache__" in p.parts:
        return False
    return any(p == r or r in p.parents for r in PROTECTED_REPO_PATHS)


# ---------------------------------------------------------------------------
# Test isolation
# ---------------------------------------------------------------------------

def test_root() -> Optional[Path]:
    value = os.environ.get(TEST_ROOT_ENV)
    return _resolve(value) if value else None


def validate_test_root(root) -> Path:
    """A disposable root: absolute, existing, under the system temp dir, outside the repository."""
    if not root:
        raise UnsafeFilesystemOperation(f"{TEST_ROOT_ENV} is not set")
    r = _resolve(root)
    if not r.is_dir():
        raise UnsafeFilesystemOperation(f"test filesystem root {r} does not exist")
    if is_within(r, BACKEND_ROOT) or is_within(BACKEND_ROOT, r):
        raise UnsafeFilesystemOperation(f"test filesystem root {r} overlaps the repository")
    if not is_within(r, tempfile.gettempdir()):
        raise UnsafeFilesystemOperation(f"test filesystem root {r} is not under the system temp directory")
    return r


def validate_settings_paths(settings, root, names: Iterable[str] = DATA_PATH_SETTINGS) -> None:
    """Fail closed unless every configured data path is inside the disposable test root."""
    r = validate_test_root(root)
    bad = [f"{n}={getattr(settings, n)}" for n in names if not is_within(getattr(settings, n), r)]
    if bad:
        raise UnsafeFilesystemOperation("data paths outside the test root: " + ", ".join(bad))


_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_hook_installed = False


def _is_write_open(mode, flags) -> bool:
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _audit(event: str, args) -> None:
    targets = ()
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        if isinstance(path, (str, bytes, os.PathLike)) and _is_write_open(mode, flags):
            targets = (path,)
    elif event in ("os.remove", "os.rmdir", "os.truncate", "os.chmod", "shutil.rmtree"):
        targets = (args[0],)
    elif event in ("os.rename", "shutil.move", "shutil.copyfile", "shutil.copytree", "os.link", "os.symlink"):
        targets = tuple(args[:2]) if event in ("os.rename", "shutil.move") else (args[1],)
    elif event == "os.mkdir":
        if not os.path.isdir(os.fsdecode(args[0])):        # exist_ok re-creation changes nothing
            targets = (args[0],)
    for t in targets:
        if isinstance(t, int):                               # fd-based call: no path to judge
            continue
        try:
            protected = is_protected_repo_path(os.fsdecode(t))
        except (TypeError, ValueError, OSError):
            continue
        if protected:
            raise UnsafeFilesystemOperation(f"blocked {event} on protected repository path {os.fsdecode(t)}")


def install_test_audit_hook() -> None:
    """Process-wide, irreversible (by design) block of writes/deletes on protected repository data."""
    global _hook_installed
    if _hook_installed:
        return
    sys.addaudithook(_audit)
    _hook_installed = True


def audit_hook_installed() -> bool:
    return _hook_installed


def remove_file_within(path, root, logger=None) -> bool:
    """
    Delete ``path`` only if it is a file inside ``root`` (Block A6.0). Paths stored in
    the database are never trusted: anything outside the configured root, a directory,
    or a missing file is left untouched. Returns True when a file was removed.
    """
    if not path:
        return False
    try:
        safe = assert_within(path, root, action="delete")
    except UnsafeFilesystemOperation as exc:
        if logger is not None:
            logger.error("UNSAFE_DELETE_REFUSED | %s", exc)
        return False
    if not safe.is_file():
        return False
    os.remove(safe)
    return True
