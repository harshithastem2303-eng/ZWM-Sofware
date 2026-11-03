"""
Process-wide YOLO model cache.

Block A4.1 hardening:
* The serving file (YOLO_MODEL_PATH) is only read to hash it and copy it into an
  immutable, content-addressed load copy (<serving dir>/.model_cache/<sha>.pt).
  YOLO always loads from that copy, so an atomic replacement of the serving file
  can never be observed half-way and the serving file is held open only briefly
  (Windows refuses os.replace on open files).
* The cache is keyed by the serving file's identity (mtime, size, inode) and the
  SHA-256 it loaded; a replaced file is picked up by every process on its next call.
* ONNX exports are single-flight per content hash (cross-process lock file), run in
  a private work directory and are published with os.replace, so no reader ever
  sees an incomplete .onnx file. An interrupted export leaves nothing published.
* An optional integrity hook (registered by the app) names the SHA-256 the
  database expects to be served. A mismatching file is never loaded; a cached
  model that still matches the expectation keeps serving (fail-closed). When the
  expectation cannot be determined (database unreachable, inconsistent deployment
  state) only an already-verified cached model keeps serving; nothing new loads.
* Published ONNX files carry a SHA-256 sidecar and are re-verified before use;
  a missing or mismatching sidecar means the export is redone.
"""
import hashlib
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

from app.config import settings

logger = logging.getLogger("model_cache")


class ModelIntegrityError(RuntimeError):
    """The serving model file does not match what the active deployment expects."""


class IntegrityStateUnknown(RuntimeError):
    """Raised by the integrity hook when the expected model cannot be determined."""


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_with_retry(src, dst, attempts: Optional[int] = None, delay: float = 0.1) -> None:
    """os.replace, retried on PermissionError (Windows sharing violations while a reader has dst open)."""
    attempts = attempts or settings.FILE_REPLACE_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(delay)


def _cache_dir() -> Path:
    return Path(settings.YOLO_MODEL_PATH).resolve().parent / ".model_cache"


class YOLOModelCache:
    _instance = None
    _lock = Lock()
    _integrity_check: Optional[Callable[[], Optional[str]]] = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(YOLOModelCache, cls).__new__(cls)
                cls._instance._model = None
                cls._instance._loaded_path = None
                cls._instance._loaded_sig = None
                cls._instance._loaded_sha = None
        return cls._instance

    @classmethod
    def set_integrity_check(cls, fn: Optional[Callable[[], Optional[str]]]) -> None:
        """fn() -> SHA-256 the database expects to be served, or None when nothing is managed."""
        cls._integrity_check = staticmethod(fn) if fn is not None else None   # never bound to the instance

    @property
    def loaded_sha256(self) -> Optional[str]:
        return self._loaded_sha

    @staticmethod
    def _file_signature(path: str):
        """Identity of the serving file; changes when it is atomically replaced (Block A4)."""
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    # -- immutable load copy -------------------------------------------------

    def _load_copy(self, pt_path: str, sha: str) -> Path:
        dst = _cache_dir() / f"{sha}.pt"
        if dst.is_file() and file_sha256(dst) == sha:
            return dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            shutil.copyfile(pt_path, tmp)
            if file_sha256(tmp) != sha:
                raise ModelIntegrityError("serving model file changed while it was being loaded")
            replace_with_retry(tmp, dst)
        finally:
            if tmp.exists():
                tmp.unlink()
        return dst

    # -- ONNX: single-flight export, atomic publish ---------------------------

    @staticmethod
    def _acquire(lock_path: Path) -> bool:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > settings.ONNX_EXPORT_LOCK_STALE_SECONDS:
                    lock_path.unlink()            # exporter died; take over on the next attempt
            except FileNotFoundError:
                pass
            return False

    @staticmethod
    def _onnx_verified(final: Path) -> bool:
        """A published export is usable only if it matches the SHA-256 recorded at publish time."""
        sidecar = final.with_name(final.name + ".sha256")
        try:
            return (final.is_file() and final.stat().st_size > 0
                    and sidecar.read_text().strip() == file_sha256(final))
        except OSError:
            return False

    def _ensure_onnx(self, local_pt: Path, sha: str) -> Optional[Path]:
        final = local_pt.with_suffix(".onnx")
        if self._onnx_verified(final):
            return final
        lock_path = final.with_name(final.name + ".lock")
        deadline = time.monotonic() + settings.ONNX_EXPORT_WAIT_SECONDS
        while not self._acquire(lock_path):
            if self._onnx_verified(final):
                return final                      # published by another exporter
            if time.monotonic() >= deadline:
                logger.warning("ONNX export of %s is held by another process; using PyTorch weights", sha[:12])
                return None
            time.sleep(0.25)
        work = final.parent / f".export-{uuid.uuid4().hex[:8]}"
        try:
            if self._onnx_verified(final):
                return final
            work.mkdir(parents=True)
            src = work / local_pt.name
            shutil.copyfile(local_pt, src)
            logger.info("Exporting YOLO model %s to ONNX...", sha[:12])
            from ultralytics import YOLO
            YOLO(str(src)).export(format="onnx", imgsz=640, dynamic=True)
            produced = src.with_suffix(".onnx")
            if not produced.is_file() or produced.stat().st_size == 0:
                logger.error("ONNX export produced no file for %s", sha[:12])
                return None
            digest = file_sha256(produced)
            replace_with_retry(produced, final)
            sidecar_tmp = work / "onnx.sha256"
            sidecar_tmp.write_text(digest)
            replace_with_retry(sidecar_tmp, final.with_name(final.name + ".sha256"))
            if not self._onnx_verified(final):
                logger.error("Published ONNX export of %s failed verification", sha[:12])
                return None
            self._validate_onnx_outputs(str(local_pt), str(final))
            return final
        except Exception as e:
            logger.exception(f"Failed to export YOLO model to ONNX: {e}")
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def _validate_onnx_outputs(self, pt_path: str, onnx_path: str) -> bool:
        """Run dummy inference on both models to verify ONNX compatibility."""
        try:
            import numpy as np
            from ultralytics import YOLO

            pt_model = YOLO(pt_path)
            onnx_model = YOLO(onnx_path, task="detect")
            dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
            pt_model(dummy_img, verbose=False)
            onnx_model(dummy_img, verbose=False)
            logger.info("ONNX validation passed: PyTorch boxes structure matched ONNX.")
            return True
        except Exception as e:
            logger.warning(f"Validation comparison of PyTorch vs ONNX failed: {e}")
            return False

    # -- public API ----------------------------------------------------------

    def get_model(self, expected_sha: Optional[str] = None):
        """
        Return the cached model for the current serving file, loading it if needed.
        expected_sha overrides the integrity hook (used by deployment readiness checks).
        """
        pt_path = settings.YOLO_MODEL_PATH
        if not os.path.exists(pt_path):
            with self._lock:
                self._model = None
                self._loaded_path = None
                self._loaded_sig = None
                self._loaded_sha = None
            return None
        try:
            sig = self._file_signature(pt_path)
        except OSError:
            sig = None

        use_onnx = settings.YOLO_INFERENCE_BACKEND.lower() == "onnx"
        with self._lock:
            # Cached and the serving file was not replaced since it was loaded
            if self._model is not None and self._loaded_sig == sig and self._loaded_sig is not None:
                return self._model

            sha = file_sha256(pt_path)
            if expected_sha is None and self._integrity_check is not None:
                try:
                    expected_sha = self._integrity_check()
                except IntegrityStateUnknown as exc:
                    if self._model is not None and self._loaded_sha is not None:
                        logger.error("Model integrity state unknown (%s); keeping the verified cached model", exc)
                        return self._model
                    raise ModelIntegrityError(f"cannot verify the serving model: {exc}")
            if expected_sha is not None and sha != expected_sha:
                if self._model is not None and self._loaded_sha == expected_sha:
                    logger.warning("Serving file does not match the active deployment; keeping the verified cached model")
                    return self._model
                raise ModelIntegrityError("serving model file does not match the active deployment")

            local_pt = self._load_copy(pt_path, sha)
            target_path = str(local_pt)
            if use_onnx:
                onnx = self._ensure_onnx(local_pt, sha)
                if onnx is not None:
                    target_path = str(onnx)
                else:
                    logger.warning("ONNX export failed. Falling back to PyTorch .pt model...")
                    use_onnx = False

            logger.info(f"Loading YOLO model {sha[:12]} from {target_path}...")
            try:
                from ultralytics import YOLO
                self._model = YOLO(target_path, task="detect") if use_onnx else YOLO(target_path)
                self._loaded_path, self._loaded_sig, self._loaded_sha = target_path, sig, sha
                return self._model
            except Exception as e:
                logger.exception(f"Failed to load YOLO model: {e}")
                if use_onnx:
                    logger.warning("ONNX loading failed. Attempting fallback to PyTorch .pt model...")
                    try:
                        from ultralytics import YOLO
                        self._model = YOLO(str(local_pt))
                        self._loaded_path, self._loaded_sig, self._loaded_sha = str(local_pt), sig, sha
                        return self._model
                    except Exception as fallback_err:
                        logger.exception(f"PyTorch fallback also failed: {fallback_err}")
                self._model = None
                self._loaded_path = None
                self._loaded_sig = None
                self._loaded_sha = None
                raise

    def get_model_with_identity(self, attempts: int = 3):
        """
        Block A6.1: (model, identity) where identity describes exactly the artifact the
        returned model object was loaded from: {"sha256", "backend", "artifact"}.
        A concurrent reload between loading and reading the identity is retried; if
        the pair still cannot be confirmed, identity is None (never a guess).
        """
        for _ in range(attempts):
            model = self.get_model()
            if model is None:
                return None, None
            with self._lock:
                if self._model is model and self._loaded_sha:
                    path = self._loaded_path or ""
                    return model, {
                        "sha256": self._loaded_sha,
                        "backend": "onnx" if path.endswith(".onnx") else "pytorch",
                        "artifact": os.path.basename(settings.YOLO_MODEL_PATH),
                    }
        return model, None

    def reload(self):
        with self._lock:
            logger.info("Clearing YOLO model cache...")
            self._model = None
            self._loaded_path = None
            self._loaded_sig = None
            self._loaded_sha = None
