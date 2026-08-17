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

def check_dimensions(image_path, min_width=640, min_height=480):
    try:
        image = Image.open(image_path)

        width, height = image.size

        if width < min_width or height < min_height:
            return {
                "status": "reject",
                "message": f"Image resolution is too low: {width}x{height}"
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

def check_blur(image_path, threshold=100):
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
                "message": f"Image is too blurry. Score: {blur_score:.2f}"
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