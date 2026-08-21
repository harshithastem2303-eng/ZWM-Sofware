"""
Annotation validation and helper service.

Validates annotation types, shape-specific point rules, and coordinate ranges.
Does NOT touch filesystem or database — pure business logic.

Supported annotation types:
    rectangle  - exactly 2 points: top-left and bottom-right corners
    polygon    - 3 or more ordered vertices
    circle     - cx, cy, r keys (r > 0)
    freehand   - 2 or more ordered points (free-drawn path)
"""
from typing import Any
from fastapi import HTTPException, status

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_TYPES: frozenset[str] = frozenset({"rectangle", "polygon", "circle", "freehand"})

_TYPE_MIN_POINTS = {
    "rectangle": 2,
    "polygon": 3,
    "freehand": 2,
}


# ---------------------------------------------------------------------------
# Public validation helpers
# ---------------------------------------------------------------------------

def validate_annotation_type(annotation_type: str) -> str:
    """
    Ensure annotation_type is one of the supported values.
    Returns the normalised (lowercased) type string.
    Raises HTTP 422 on failure.
    """
    normalised = annotation_type.strip().lower()
    if normalised not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported annotation type '{annotation_type}'. "
                f"Allowed: {sorted(SUPPORTED_TYPES)}"
            ),
        )
    return normalised


def validate_label_data(annotation_type: str, label_data: dict) -> dict:
    """
    Validate the label_data payload for the given annotation type.

    Returns the (possibly normalised) label_data dict.
    Raises HTTP 422 with a descriptive message on failure.
    """
    if not isinstance(label_data, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="label_data must be a JSON object.",
        )

    if annotation_type == "circle":
        return _validate_circle(label_data)
    else:
        return _validate_points_shape(annotation_type, label_data)


# ---------------------------------------------------------------------------
# Shape-specific validators
# ---------------------------------------------------------------------------

def _validate_circle(label_data: dict) -> dict:
    """Validate circle: requires cx, cy, r keys; r must be > 0."""
    for key in ("cx", "cy", "r"):
        if key not in label_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Circle annotation requires '{key}' in label_data.",
            )
    try:
        cx = float(label_data["cx"])
        cy = float(label_data["cy"])
        r = float(label_data["r"])
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Circle cx, cy, r must be numeric values.",
        )
    if r <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Circle radius must be > 0, got {r}.",
        )
    return {"cx": cx, "cy": cy, "r": r}


def _validate_points_shape(annotation_type: str, label_data: dict) -> dict:
    """Validate polygon/rectangle/freehand: requires a 'points' list."""
    if "points" not in label_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{annotation_type.capitalize()} annotation requires a 'points' list in label_data.",
        )

    points = label_data["points"]
    if not isinstance(points, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'points' must be a list of {x, y} objects.",
        )

    min_pts = _TYPE_MIN_POINTS[annotation_type]
    if len(points) < min_pts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{annotation_type.capitalize()} requires at least {min_pts} point(s), "
                f"got {len(points)}."
            ),
        )

    if annotation_type == "rectangle" and len(points) != 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rectangle annotation must have exactly 2 points (top-left, bottom-right).",
        )

    validated_points = []
    for i, pt in enumerate(points):
        if not isinstance(pt, dict) or "x" not in pt or "y" not in pt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Point {i} must be an object with 'x' and 'y' keys.",
            )
        try:
            x = float(pt["x"])
            y = float(pt["y"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Point {i}: x and y must be numeric.",
            )
        if x < 0 or y < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Point {i}: coordinates cannot be negative (got x={x}, y={y}).",
            )
        validated_points.append({"x": x, "y": y})

    # Build the normalised payload; preserve any extra keys the caller included
    normalised = {k: v for k, v in label_data.items() if k != "points"}
    normalised["points"] = validated_points
    return normalised
