import cv2
from PIL import Image
import hashlib


# --------------------------------------------------
# 1. CHECK IMAGE FORMAT
# --------------------------------------------------

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def check_format(image_path):
    try:
        image = Image.open(image_path)

        if image.format not in ALLOWED_FORMATS:
            return {
                "status": "reject",
                "message": f"Unsupported format: {image.format}"
            }

        return {
            "status": "pass",
            "message": f"Valid format: {image.format}"
        }

    except Exception:
        return {
            "status": "reject",
            "message": "Invalid or unreadable image file"
        }


# --------------------------------------------------
# 2. CHECK CORRUPTED IMAGE
# --------------------------------------------------

def check_corrupted(image_path):
    try:
        image = Image.open(image_path)
        image.verify()

        return {
            "status": "pass",
            "message": "Image is valid and not corrupted"
        }

    except Exception:
        return {
            "status": "reject",
            "message": "Image is corrupted"
        }


# --------------------------------------------------
# 3. CHECK IMAGE DIMENSIONS
# --------------------------------------------------

def check_dimensions(image_path, min_width=200, min_height=200):
    try:
        image = Image.open(image_path)

        width, height = image.size

        if width < min_width or height < min_height:
            return {
                "status": "reject",
                "message": f"Image resolution is too low ({width}x{height}). Minimum required resolution is {min_width}x{min_height}."
            }

        return {
            "status": "pass",
            "message": f"Resolution is valid: {width}x{height}"
        }

    except Exception:
        return {
            "status": "reject",
            "message": "Could not check image dimensions"
        }


# --------------------------------------------------
# 4. CHECK BLUR
# --------------------------------------------------

def check_blur(image_path, threshold=15):
    try:
        image = cv2.imread(image_path)

        if image is None:
            return {
                "status": "reject",
                "message": "Unable to read image"
            }

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        blur_score = cv2.Laplacian(
            gray,
            cv2.CV_64F
        ).var()

        if blur_score < threshold:
            return {
                "status": "reject",
                "message": f"Image is too blurry. Score: {blur_score:.2f} (Minimum required: {threshold})"
            }

        return {
            "status": "pass",
            "message": f"Image is clear. Score: {blur_score:.2f}"
        }

    except Exception:
        return {
            "status": "reject",
            "message": "Could not check image blur"
        }


# --------------------------------------------------
# 5. GENERATE FILE HASH
# --------------------------------------------------

def get_file_hash(image_path):
    try:
        sha256 = hashlib.sha256()

        with open(image_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                sha256.update(chunk)

        return sha256.hexdigest()

    except Exception:
        return None


# --------------------------------------------------
# 6. CHECK EXACT DUPLICATE
# --------------------------------------------------

def check_duplicate(image_path, existing_hashes=None):
    """
    existing_hashes should contain hashes
    already stored in your database.
    """

    if existing_hashes is None:
        existing_hashes = set()

    file_hash = get_file_hash(image_path)

    if file_hash is None:
        return {
            "status": "reject",
            "message": "Could not generate image hash"
        }

    if file_hash in existing_hashes:
        return {
            "status": "reject",
            "message": "Duplicate image detected"
        }

    return {
        "status": "pass",
        "message": "Image is unique",
        "hash": file_hash
    }


# --------------------------------------------------
# 7. COMPLETE IMAGE VALIDATION
# --------------------------------------------------

def validate_image(image_path, existing_hashes=None):

    results = {}

    results["format"] = check_format(image_path)

    if results["format"]["status"] == "reject":
        return {
            "valid": False,
            "reason": "format",
            "checks": results
        }

    results["corrupted"] = check_corrupted(image_path)

    if results["corrupted"]["status"] == "reject":
        return {
            "valid": False,
            "reason": "corrupted",
            "checks": results
        }

    results["dimensions"] = check_dimensions(image_path)

    if results["dimensions"]["status"] == "reject":
        return {
            "valid": False,
            "reason": "dimensions",
            "checks": results
        }

    results["blur"] = check_blur(image_path)

    if results["blur"]["status"] == "reject":
        return {
            "valid": False,
            "reason": "blur",
            "checks": results
        }

    results["duplicate"] = check_duplicate(
        image_path,
        existing_hashes
    )

    if results["duplicate"]["status"] == "reject":
        return {
            "valid": False,
            "reason": "duplicate",
            "checks": results
        }

    return {
        "valid": True,
        "reason": None,
        "checks": results
    }


# --------------------------------------------------
# 8. AI CATEGORY MATCH VALIDATION
# --------------------------------------------------

def detections_from_results(results, names) -> list:
    """Every box exactly as the model reported it (Block A6.1 prediction evidence)."""
    out = []
    for res in results or []:
        boxes = getattr(res, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            cls_id = int(box.cls[0])
            bbox = box.xyxy[0]
            out.append({"class_id": cls_id, "label": str(names.get(cls_id)) if names.get(cls_id) is not None else None,
                        "confidence": float(box.conf[0]),
                        "bbox": [float(v) for v in (bbox.tolist() if hasattr(bbox, "tolist") else bbox)]})
    return out


def _with_inference(inference: dict, result: dict) -> dict:
    """Attach the inference evidence (internal key, consumed by the upload route)."""
    result["_inference"] = inference
    return result


def validate_ai_category_match(image_path: str, selected_category_name: str) -> dict:
    """
    Independently validates the actual image against the user-selected category using AI model inference.
    
    Validation Rules:
    1. If the selected category is not supported by the deployed YOLO model:
       -> validation_result = "MODEL_CLASS_NOT_SUPPORTED"
       -> status = "pending_admin_review"
    2. If AI model runs inference:
       - Confidence >= 80% and predicted class matches selected class -> AUTO_ACCEPTED ("approved")
       - Confidence 50-79% and predicted class matches selected class -> NEEDS_HUMAN_REVIEW ("pending_admin_review")
       - Confidence < 50% -> LOW_CONFIDENCE ("pending_admin_review")
       - High confidence prediction of a DIFFERENT class -> CLASS_MISMATCH ("pending_admin_review")
    """
    try:
        from app.services.model_cache import YOLOModelCache
        model_cache = YOLOModelCache()
        # Block A6.1: the model object and the identity of the artifact it was loaded
        # from are captured together, so the prediction is attributed to exactly it.
        model, identity = model_cache.get_model_with_identity()
    except Exception:
        model, identity = None, None

    if model is None or not hasattr(model, "names") or not model.names:
        return {
            "predicted_category": None,
            "confidence": 0.0,
            "validation_result": "MODEL_CLASS_NOT_SUPPORTED",
            "status": "pending_admin_review",
            "reason": "This class is not currently supported by the deployed AI model.",
            "is_validated": False,
        }

    # Normalize category names for matching
    model_labels = {str(k): str(v).lower().strip() for k, v in model.names.items()}
    target_category_norm = selected_category_name.lower().strip()

    # Check if target category exists in model's labels or partial synonyms
    category_supported = False
    target_model_class_ids = []

    for class_id, label in model_labels.items():
        if label in target_category_norm or target_category_norm in label:
            category_supported = True
            target_model_class_ids.append(int(class_id))
        elif target_category_norm in ['plastic', 'plastic waste', 'plastic bottle'] and 'bottle' in label:
            category_supported = True
            target_model_class_ids.append(int(class_id))
        elif target_category_norm in ['glass', 'glass containers', 'glass bottle'] and 'bottle' in label:
            category_supported = True
            target_model_class_ids.append(int(class_id))
        elif target_category_norm in ['organic', 'food', 'food waste'] and label in ['apple', 'banana', 'orange', 'sandwich', 'broccoli', 'carrot']:
            category_supported = True
            target_model_class_ids.append(int(class_id))

    if not category_supported:
        return {
            "predicted_category": None,
            "confidence": 0.0,
            "validation_result": "MODEL_CLASS_NOT_SUPPORTED",
            "status": "pending_admin_review",
            "reason": "This class is not currently supported by the deployed AI model.",
            "is_validated": False,
        }

    # Run inference using model
    inference = {"identity": identity, "class_names": {str(k): str(v) for k, v in model.names.items()},
                 "params": {"verbose": False}, "detections": []}
    try:
        results = model(image_path, verbose=False)
        inference["detections"] = detections_from_results(results, model.names)
        top_conf = 0.0
        top_cls_id = None

        for res in results:
            if hasattr(res, "boxes") and len(res.boxes) > 0:
                for box in res.boxes:
                    conf = float(box.conf[0])
                    if conf > top_conf:
                        top_conf = conf
                        top_cls_id = int(box.cls[0])

        if top_cls_id is None or top_conf < 0.50:
            return _with_inference(inference, {
                "predicted_category": model.names.get(top_cls_id, "Unknown") if top_cls_id is not None else None,
                "confidence": round(top_conf, 4),
                "validation_result": "LOW_CONFIDENCE",
                "status": "pending_admin_review",
                "reason": f"Low AI confidence score ({top_conf:.1%}).",
                "is_validated": False,
            })

        predicted_label = model.names.get(top_cls_id, "Unknown")

        # Check if predicted class matches user selected category
        is_match = (
            top_cls_id in target_model_class_ids or
            predicted_label.lower() in target_category_norm or
            target_category_norm in predicted_label.lower()
        )

        if is_match:
            if top_conf >= 0.80:
                return _with_inference(inference, {
                    "predicted_category": predicted_label,
                    "confidence": round(top_conf, 4),
                    "validation_result": "AUTO_ACCEPTED",
                    "status": "approved",
                    "reason": f"Auto-accepted with {top_conf:.1%} confidence match.",
                    "is_validated": True,
                })
            else:
                return _with_inference(inference, {
                    "predicted_category": predicted_label,
                    "confidence": round(top_conf, 4),
                    "validation_result": "NEEDS_HUMAN_REVIEW",
                    "status": "pending_admin_review",
                    "reason": f"Uncertain prediction ({top_conf:.1%}). Sent for admin review.",
                    "is_validated": False,
                })
        else:
            return _with_inference(inference, {
                "predicted_category": predicted_label,
                "confidence": round(top_conf, 4),
                "validation_result": "CLASS_MISMATCH",
                "status": "pending_admin_review",
                "reason": f"Class mismatch: User selected '{selected_category_name}', AI predicted '{predicted_label}' ({top_conf:.1%}).",
                "is_validated": False,
            })

    except Exception as e:
        inference["error"] = type(e).__name__
        return _with_inference(inference, {
            "predicted_category": None,
            "confidence": 0.0,
            "validation_result": "NEEDS_HUMAN_REVIEW",
            "status": "pending_admin_review",
            "reason": f"Inference processing error: {str(e)}",
            "is_validated": False,
        })
