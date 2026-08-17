import os
import json

def convert_json_to_yolo(json_path, target_txt_path, class_code, img_width, img_height):
    """Converts standard annotation JSON polygon/bbox coordinates into YOLO normalized format"""
    with open(json_path, 'r') as f:
        data = json.load(f)

    # Example: Converting polygon points [(x1, y1), (x2, y2), ...]
    normalized_points = []
    for point in data['points']:
        norm_x = point['x'] / img_width
        norm_y = point['y'] / img_height
        normalized_points.extend([f"{norm_x:.6f}", f"{norm_y:.6f}"])

    yolo_str = f"{class_code} " + " ".join(normalized_points) + "\n"

    with open(target_txt_path, 'w') as f:
        f.write(yolo_str)