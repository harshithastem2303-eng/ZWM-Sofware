"""
Annotation conversion service — YOLO bounding-box utilities.

Provides functions to:
  - Derive an axis-aligned bounding box from any annotation shape.
  - Convert that bounding box to YOLO normalised format.
  - Produce a complete YOLO annotation line for a single annotation record.

The original annotation data is NEVER modified by this service.
All conversions are read-only transforms for dataset export purposes.

YOLO format (per line):
    <class_id> <x_center> <y_center> <width> <height>
    where all coordinate values are normalised to [0, 1] relative to image size.
"""
from typing import Optional


# ---------------------------------------------------------------------------
# Bounding-box derivation
# ---------------------------------------------------------------------------

def shape_to_bbox(annotation_type: str, label_data: dict) -> Optional[tuple[float, float, float, float]]:
    """
    Derive an axis-aligned bounding box from annotation shape data.

    Returns (x_min, y_min, x_max, y_max) in pixel coordinates,
    or None if the data is insufficient.

    Parameters
    ----------
    annotation_type : str
        One of: rectangle, polygon, circle, freehand
    label_data : dict
        The stored label_data_json value from the Annotation record.
    """
    if not label_data:
        return None

    try:
        if annotation_type == "circle":
            cx = float(label_data["cx"])
            cy = float(label_data["cy"])
            r = float(label_data["r"])
            return (cx - r, cy - r, cx + r, cy + r)

        # rectangle / polygon / freehand — all use a "points" list
        points = label_data.get("points", [])
        if not points:
            return None

        xs = [float(p["x"]) for p in points]
        ys = [float(p["y"]) for p in points]
        return (min(xs), min(ys), max(xs), max(ys))

    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# YOLO normalisation
# ---------------------------------------------------------------------------

def bbox_to_yolo(
    bbox: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
    class_id: int,
) -> str:
    """
    Convert a pixel bounding box to a YOLO annotation line.

    Parameters
    ----------
    bbox         : (x_min, y_min, x_max, y_max) in pixels
    image_width  : image width in pixels
    image_height : image height in pixels
    class_id     : integer class identifier

    Returns
    -------
    str  - e.g. "0 0.5000 0.5000 0.3000 0.4000"
    """
    x_min, y_min, x_max, y_max = bbox
    x_center = ((x_min + x_max) / 2) / image_width
    y_center = ((y_min + y_max) / 2) / image_height
    width    = (x_max - x_min) / image_width
    height   = (y_max - y_min) / image_height

    # Clamp to [0, 1]
    x_center = max(0.0, min(1.0, x_center))
    y_center = max(0.0, min(1.0, y_center))
    width    = max(0.0, min(1.0, width))
    height   = max(0.0, min(1.0, height))

    return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


def annotation_to_yolo_line(
    annotation_type: str,
    label_data: dict,
    image_width: int,
    image_height: int,
    class_id: int,
) -> Optional[str]:
    """
    Full pipeline: shape data -> bounding box -> YOLO line.

    Returns None if conversion is not possible (e.g. missing data).
    """
    bbox = shape_to_bbox(annotation_type, label_data)
    if bbox is None:
        return None
    return bbox_to_yolo(bbox, image_width, image_height, class_id)


# ---------------------------------------------------------------------------
# Bounding-box dict helper (for API responses)
# ---------------------------------------------------------------------------

def shape_to_bbox_dict(annotation_type: str, label_data: dict) -> Optional[dict]:
    """
    Return the bounding box as a readable dict, or None.

    Keys: x_min, y_min, x_max, y_max
    """
    result = shape_to_bbox(annotation_type, label_data)
    if result is None:
        return None
    x_min, y_min, x_max, y_max = result
    return {
        "x_min": round(x_min, 4),
        "y_min": round(y_min, 4),
        "x_max": round(x_max, 4),
        "y_max": round(y_max, 4),
    }
