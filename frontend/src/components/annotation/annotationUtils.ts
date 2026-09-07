import { Point, CircleData, LocalAnnotation, Dimensions } from './types';

/**
 * Convert mouse display coordinates on canvas to native image resolution coordinates.
 */
export function screenToImageCoords(
  screenPt: Point,
  displayDim: Dimensions,
  naturalDim: Dimensions
): Point {
  if (displayDim.width === 0 || displayDim.height === 0) return screenPt;
  const scaleX = naturalDim.width / displayDim.width;
  const scaleY = naturalDim.height / displayDim.height;
  return {
    x: Math.round(screenPt.x * scaleX),
    y: Math.round(screenPt.y * scaleY),
  };
}

/**
 * Convert native image resolution coordinates to canvas display coordinates.
 */
export function imageToScreenCoords(
  imagePt: Point,
  displayDim: Dimensions,
  naturalDim: Dimensions
): Point {
  if (naturalDim.width === 0 || naturalDim.height === 0) return imagePt;
  const scaleX = displayDim.width / naturalDim.width;
  const scaleY = displayDim.height / naturalDim.height;
  return {
    x: Math.round(imagePt.x * scaleX),
    y: Math.round(imagePt.y * scaleY),
  };
}

/**
 * Render a saved annotation onto the 2D canvas context.
 */
export function drawShape(
  ctx: CanvasRenderingContext2D,
  ann: LocalAnnotation,
  displayDim: Dimensions,
  naturalDim: Dimensions,
  isSelected = false
) {
  if (ann.visible === false) return;

  const color = ann.color || '#22c55e';
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = isSelected ? 3.5 : 2.5;
  ctx.fillStyle = color + '25';

  if (isSelected) {
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
  }

  // Draw Circle
  if (ann.type === 'circle' && ann.circle) {
    const centerScreen = imageToScreenCoords({ x: ann.circle.cx, y: ann.circle.cy }, displayDim, naturalDim);
    const scaleX = displayDim.width / naturalDim.width;
    const rScreen = ann.circle.r * scaleX;

    ctx.beginPath();
    ctx.arc(centerScreen.x, centerScreen.y, rScreen, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Center dot
    ctx.beginPath();
    ctx.arc(centerScreen.x, centerScreen.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }
  // Draw Rectangle (stored as corner points)
  else if (ann.type === 'rectangle' && ann.points && ann.points.length >= 2) {
    const screenPts = ann.points.map((p) => imageToScreenCoords(p, displayDim, naturalDim));
    const xs = screenPts.map((p) => p.x);
    const ys = screenPts.map((p) => p.y);
    const x = Math.min(...xs);
    const y = Math.min(...ys);
    const w = Math.max(...xs) - x;
    const h = Math.max(...ys) - y;

    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
  }
  // Draw Polygon / AI Polygon / Freehand
  else if (ann.points && ann.points.length >= 2) {
    const screenPts = ann.points.map((p) => imageToScreenCoords(p, displayDim, naturalDim));
    ctx.beginPath();
    ctx.moveTo(screenPts[0].x, screenPts[0].y);
    for (let i = 1; i < screenPts.length; i++) {
      ctx.lineTo(screenPts[i].x, screenPts[i].y);
    }
    if (ann.type !== 'freehand') {
      ctx.closePath();
    }
    ctx.fill();
    ctx.stroke();

    // Vertex dots for polygons
    if (ann.type === 'polygon' || ann.type === 'ai_polygon') {
      screenPts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      });
    }
  }

  // Draw Label tag
  if (ann.label && ((ann.points && ann.points.length > 0) || ann.circle)) {
    let labelX = 0;
    let labelY = 0;
    if (ann.circle) {
      const centerScreen = imageToScreenCoords({ x: ann.circle.cx, y: ann.circle.cy }, displayDim, naturalDim);
      labelX = centerScreen.x;
      labelY = centerScreen.y - (ann.circle.r * (displayDim.width / naturalDim.width)) - 6;
    } else if (ann.points && ann.points.length > 0) {
      const screenPts = ann.points.map((p) => imageToScreenCoords(p, displayDim, naturalDim));
      labelX = screenPts[0].x;
      labelY = screenPts[0].y - 6;
    }

    ctx.font = 'bold 12px Inter, sans-serif';
    const tagText = `${ann.aiGenerated ? '✨ ' : ''}${ann.label}`;
    const metrics = ctx.measureText(tagText);
    ctx.fillStyle = color;
    ctx.fillRect(labelX - 2, labelY - 14, metrics.width + 8, 18);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(tagText, labelX + 2, labelY);
  }

  ctx.restore();
}

/**
 * Draw live vector preview while drawing shapes.
 */
export function drawPreview(
  ctx: CanvasRenderingContext2D,
  tool: string,
  currentPoints: Point[],
  currentCircle: CircleData | null,
  color: string,
  mousePos: Point | null
) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 3]);
  ctx.fillStyle = color + '15';

  if (tool === 'rectangle' && currentPoints.length >= 2) {
    const [p1, p2] = currentPoints;
    const x = Math.min(p1.x, p2.x);
    const y = Math.min(p1.y, p2.y);
    const w = Math.abs(p2.x - p1.x);
    const h = Math.abs(p2.y - p1.y);
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
  } else if (tool === 'circle' && currentCircle) {
    ctx.beginPath();
    ctx.arc(currentCircle.cx, currentCircle.cy, currentCircle.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Center indicator
    ctx.beginPath();
    ctx.arc(currentCircle.cx, currentCircle.cy, 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  } else if (tool === 'freehand' && currentPoints.length >= 2) {
    ctx.beginPath();
    ctx.moveTo(currentPoints[0].x, currentPoints[0].y);
    for (let i = 1; i < currentPoints.length; i++) {
      ctx.lineTo(currentPoints[i].x, currentPoints[i].y);
    }
    ctx.stroke();
  } else if (tool === 'polygon' && currentPoints.length >= 1) {
    ctx.beginPath();
    ctx.moveTo(currentPoints[0].x, currentPoints[0].y);
    for (let i = 1; i < currentPoints.length; i++) {
      ctx.lineTo(currentPoints[i].x, currentPoints[i].y);
    }

    // Live preview line connecting to current mouse position
    if (mousePos) {
      ctx.lineTo(mousePos.x, mousePos.y);
    }
    ctx.stroke();

    // Vertex dots
    currentPoints.forEach((p, idx) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, idx === 0 ? 6 : 4, 0, Math.PI * 2);
      ctx.fillStyle = idx === 0 ? '#ef4444' : color;
      ctx.fill();
    });
  }

  ctx.restore();
}
