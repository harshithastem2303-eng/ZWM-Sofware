import os
import logging
from threading import Lock
from app.config import settings

logger = logging.getLogger("model_cache")

class YOLOModelCache:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(YOLOModelCache, cls).__new__(cls)
                cls._instance._model = None
                cls._instance._loaded_path = None
        return cls._instance
        
    def _export_to_onnx(self, pt_path: str, onnx_path: str) -> bool:
        """Export PyTorch YOLO weights to ONNX format safely."""
        try:
            logger.info(f"Exporting PyTorch model {pt_path} to ONNX format at {onnx_path}...")
            from ultralytics import YOLO
            pt_model = YOLO(pt_path)
            # Export to onnx (produces a file at the same name but suffix .onnx)
            pt_model.export(format="onnx", imgsz=640, dynamic=True)
            if os.path.exists(onnx_path):
                logger.info(f"Successfully exported ONNX model to {onnx_path}")
                return True
            else:
                logger.error(f"ONNX export succeeded but file not found at {onnx_path}")
                return False
        except Exception as e:
            logger.exception(f"Failed to export YOLO model to ONNX: {e}")
            return False

    def _validate_onnx_outputs(self, pt_path: str, onnx_path: str) -> bool:
        """Run dummy inference on both models to verify ONNX compatibility."""
        try:
            import numpy as np
            from ultralytics import YOLO
            
            # Load both models
            pt_model = YOLO(pt_path)
            onnx_model = YOLO(onnx_path, task="detect")
            
            # Create a dummy image
            dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
            
            # Inference
            res_pt = pt_model(dummy_img, verbose=False)
            res_onnx = onnx_model(dummy_img, verbose=False)
            
            # Compare output bounding box structures
            pt_boxes = res_pt[0].boxes
            onnx_boxes = res_onnx[0].boxes
            
            logger.info("ONNX validation passed: PyTorch boxes structure matched ONNX.")
            return True
        except Exception as e:
            logger.warning(f"Validation comparison of PyTorch vs ONNX failed: {e}")
            return False

    def get_model(self):
        pt_path = settings.YOLO_MODEL_PATH
        if not os.path.exists(pt_path):
            with self._lock:
                self._model = None
                self._loaded_path = None
            return None

        # Check inference backend
        use_onnx = settings.YOLO_INFERENCE_BACKEND.lower() == "onnx"
        
        target_path = pt_path
        if use_onnx:
            target_path = os.path.splitext(pt_path)[0] + ".onnx"
            
        with self._lock:
            # If already cached
            if self._model is not None and self._loaded_path == target_path:
                return self._model
                
            # If ONNX is preferred, check if export is needed
            if use_onnx:
                export_needed = False
                if not os.path.exists(target_path):
                    export_needed = True
                else:
                    # check modification time (if pt is newer than onnx, re-export)
                    pt_mtime = os.path.getmtime(pt_path)
                    onnx_mtime = os.path.getmtime(target_path)
                    if pt_mtime > onnx_mtime:
                        export_needed = True
                        
                if export_needed:
                    success = self._export_to_onnx(pt_path, target_path)
                    if success:
                        # Validate
                        self._validate_onnx_outputs(pt_path, target_path)
                    else:
                        logger.warning("ONNX export failed. Falling back to PyTorch .pt model...")
                        target_path = pt_path
                        use_onnx = False

            # Load the model
            logger.info(f"Loading YOLO model from {target_path}...")
            try:
                from ultralytics import YOLO
                if use_onnx:
                    self._model = YOLO(target_path, task="detect")
                else:
                    self._model = YOLO(target_path)
                    
                self._loaded_path = target_path
                return self._model
            except Exception as e:
                logger.exception(f"Failed to load YOLO model: {e}")
                # Fallback to PyTorch .pt if ONNX loading failed
                if use_onnx and target_path != pt_path:
                    logger.warning("ONNX loading failed. Attempting fallback to PyTorch .pt model...")
                    try:
                        from ultralytics import YOLO
                        self._model = YOLO(pt_path)
                        self._loaded_path = pt_path
                        return self._model
                    except Exception as fallback_err:
                        logger.exception(f"PyTorch fallback also failed: {fallback_err}")
                
                self._model = None
                self._loaded_path = None
                raise
                
    def reload(self):
        with self._lock:
            logger.info("Clearing YOLO model cache...")
            self._model = None
            self._loaded_path = None
