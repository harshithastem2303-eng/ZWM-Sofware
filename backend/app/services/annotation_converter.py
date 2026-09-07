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

    Supports shapes: rectangle, polygon, circle, freehand, ai_polygon.
    Handles both dict points [{"x": x, "y": y}] and pair points [[x, y]],
    as well as explicit bbox structures.

    Returns (x_min, y_min, x_max, y_max) in pixel coordinates,
    or None if the data is insufficient.
    """
    if not label_data or not isinstance(label_data, dict):
        return None

    try:
        # Check explicit bbox array fallback if present: [x_min, y_min, x_max, y_max]
        if "bbox" in label_data and isinstance(label_data["bbox"], (list, tuple)) and len(label_data["bbox"]) == 4:
            b = label_data["bbox"]
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))

        norm_type = (annotation_type or "").lower()

        # Circle shape
        if norm_type == "circle" or "r" in label_data or "radius" in label_data:
            cx = float(label_data.get("cx") or (label_data.get("center", {}) or {}).get("x", 0))
            cy = float(label_data.get("cy") or (label_data.get("center", {}) or {}).get("y", 0))
            r = float(label_data.get("r") or label_data.get("radius", 0))
            return (cx - r, cy - r, cx + r, cy + r)

        # Points-based shapes: rectangle, polygon, freehand, ai_polygon
        points = label_data.get("points", [])
        if not points:
            return None

        xs, ys = [], []
        for p in points:
            if isinstance(p, dict) and "x" in p and "y" in p:
                xs.append(float(p["x"]))
                ys.append(float(p["y"]))
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                xs.append(float(p[0]))
                ys.append(float(p[1]))

        if not xs or not ys:
            return None

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
