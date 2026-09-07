import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  AnnotationType,
  Point,
  CircleData,
  LocalAnnotation,
  Dimensions,
} from './types';
import {
  screenToImageCoords,
  imageToScreenCoords,
  drawShape,
  drawPreview,
} from './annotationUtils';

export interface LocalAnnotationCanvasProps {
  imageSrc: string;
  activeTool: AnnotationTool;
  annotations: LocalAnnotation[];
  onAddAnnotation: (ann: LocalAnnotation) => void;
  onSelectAnnotation?: (id: string | null) => void;
  onAIClick?: (imagePt: Point) => Promise<Point[] | null | undefined>;
  selectedId?: string | null;
  isVisible?: boolean;
  activeColor?: string;
  activeLabel?: string;
  className?: string;
  style?: React.CSSProperties;
}

export type AnnotationTool = AnnotationType | 'select';

const TOOL_COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

export const LocalAnnotationCanvas: React.FC<LocalAnnotationCanvasProps> = ({
  imageSrc,
  activeTool,
  annotations,
  onAddAnnotation,
  onSelectAnnotation,
  onAIClick,
  selectedId = null,
  isVisible = true,
  activeColor,
  activeLabel = 'Object',
  className = '',
  style,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const [imageLoaded, setImageLoaded] = useState(false);
  const [displayDim, setDisplayDim] = useState<Dimensions>({ width: 0, height: 0 });
  const [naturalDim, setNaturalDim] = useState<Dimensions>({ width: 0, height: 0 });

  // In-progress drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [currentScreenPoints, setCurrentScreenPoints] = useState<Point[]>([]);
  const [currentImagePoints, setCurrentImagePoints] = useState<Point[]>([]);
  const [currentCircleScreen, setCurrentCircleScreen] = useState<CircleData | null>(null);
  const [mousePosScreen, setMousePosScreen] = useState<Point | null>(null);
  const [isAiLoading, setIsAiLoading] = useState(false);

  // Load image & calculate fit scale
  useEffect(() => {
    if (!imageSrc) return;
    setImageLoaded(false);

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      setNaturalDim({ width: img.naturalWidth, height: img.naturalHeight });

      const container = containerRef.current;
      if (!container) return;

      const containerW = container.clientWidth || 800;
      const containerH = container.clientHeight || 600;
      const scale = Math.min(containerW / img.naturalWidth, containerH / img.naturalHeight, 1);
      const displayW = Math.round(img.naturalWidth * scale);
      const displayH = Math.round(img.naturalHeight * scale);

      setDisplayDim({ width: displayW, height: displayH });
      setImageLoaded(true);
    };
    img.src = imageSrc;
  }, [imageSrc]);

  // Redraw canvas
  const redrawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !imageLoaded) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    // Draw saved annotations if visible
    if (isVisible) {
      annotations.forEach((ann) => {
        drawShape(ctx, ann, displayDim, naturalDim, ann.id === selectedId);
      });
    }

    // Draw in-progress preview
    if (currentScreenPoints.length > 0 || currentCircleScreen) {
      const color = activeColor || TOOL_COLORS[annotations.length % TOOL_COLORS.length];
      drawPreview(
        ctx,
        activeTool,
        currentScreenPoints,
        currentCircleScreen,
        color,
        mousePosScreen
      );
    }
  }, [
    imageLoaded,
    isVisible,
    annotations,
    displayDim,
    naturalDim,
    selectedId,
    currentScreenPoints,
    currentCircleScreen,
    activeTool,
    activeColor,
    mousePosScreen,
  ]);

  useEffect(() => {
    redrawCanvas();
  }, [redrawCanvas]);

  function getCanvasCoords(e: React.MouseEvent): Point {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  }

  // Handle AI Click
  const handleAIClickInternal = async (screenPt: Point) => {
    if (!onAIClick || isAiLoading) return;
    const imgPt = screenToImageCoords(screenPt, displayDim, naturalDim);

    setIsAiLoading(true);
    try {
      const resultPoints = await onAIClick(imgPt);
      if (resultPoints && resultPoints.length >= 3) {
        const color = activeColor || TOOL_COLORS[annotations.length % TOOL_COLORS.length];
        const newAnn: LocalAnnotation = {
          id: `ann-ai-${Date.now()}`,
          type: 'ai_polygon',
          points: resultPoints, // Stored in native image coordinates!
          label: activeLabel || 'AI Object',
          color,
          aiGenerated: true,
          visible: true,
        };
        onAddAnnotation(newAnn);
      }
    } catch (err) {
      console.error('AI Polygon click error:', err);
    } finally {
      setIsAiLoading(false);
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (activeTool === 'select' || isAiLoading) return;
    const screenPt = getCanvasCoords(e);
    const imagePt = screenToImageCoords(screenPt, displayDim, naturalDim);

    // AI Polygon Tool
    if (activeTool === 'ai_polygon') {
      handleAIClickInternal(screenPt);
      return;
    }

    // Polygon Tool: check if click closes polygon (within 10px of start point)
    if (activeTool === 'polygon' && currentScreenPoints.length >= 3) {
      const startPt = currentScreenPoints[0];
      const dist = Math.hypot(screenPt.x - startPt.x, screenPt.y - startPt.y);
      if (dist <= 10) {
        finishPolygon();
        return;
      }
    }

    if (activeTool === 'rectangle' || activeTool === 'circle' || activeTool === 'freehand') {
      setCurrentScreenPoints([screenPt]);
      setCurrentImagePoints([imagePt]);
      setIsDrawing(true);
    } else if (activeTool === 'polygon') {
      setCurrentScreenPoints((prev) => [...prev, screenPt]);
      setCurrentImagePoints((prev) => [...prev, imagePt]);
      if (!isDrawing) setIsDrawing(true);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const screenPt = getCanvasCoords(e);
    setMousePosScreen(screenPt);

    if (!isDrawing || activeTool === 'ai_polygon') return;
    const imagePt = screenToImageCoords(screenPt, displayDim, naturalDim);

    if (activeTool === 'rectangle') {
      setCurrentScreenPoints([currentScreenPoints[0], screenPt]);
      setCurrentImagePoints([currentImagePoints[0], imagePt]);
    } else if (activeTool === 'circle') {
      const centerScreen = currentScreenPoints[0];
      const rScreen = Math.hypot(screenPt.x - centerScreen.x, screenPt.y - centerScreen.y);
      setCurrentCircleScreen({ cx: centerScreen.x, cy: centerScreen.y, r: rScreen });
    } else if (activeTool === 'freehand') {
      setCurrentScreenPoints((prev) => [...prev, screenPt]);
      setCurrentImagePoints((prev) => [...prev, imagePt]);
    }
  };

  const handleMouseUp = (e: React.MouseEvent) => {
    if (!isDrawing || activeTool === 'ai_polygon') return;
    const screenPt = getCanvasCoords(e);
    const imagePt = screenToImageCoords(screenPt, displayDim, naturalDim);

    const color = activeColor || TOOL_COLORS[annotations.length % TOOL_COLORS.length];

    if (activeTool === 'rectangle') {
      const finalImagePoints = [currentImagePoints[0], imagePt];
      const newAnn: LocalAnnotation = {
        id: `ann-rect-${Date.now()}`,
        type: 'rectangle',
        points: finalImagePoints, // Stored in image coordinates
        label: activeLabel,
        color,
        visible: true,
      };
      onAddAnnotation(newAnn);
      resetDrawingState();
    } else if (activeTool === 'circle') {
      const centerImage = currentImagePoints[0];
      const rImage = Math.hypot(imagePt.x - centerImage.x, imagePt.y - centerImage.y);
      const newAnn: LocalAnnotation = {
        id: `ann-circle-${Date.now()}`,
        type: 'circle',
        circle: { cx: centerImage.x, cy: centerImage.y, r: Math.round(rImage) }, // Stored in image coordinates
        label: activeLabel,
        color,
        visible: true,
      };
      onAddAnnotation(newAnn);
      resetDrawingState();
    } else if (activeTool === 'freehand') {
      const finalImagePoints = [...currentImagePoints, imagePt];
      const newAnn: LocalAnnotation = {
        id: `ann-freehand-${Date.now()}`,
        type: 'freehand',
        points: finalImagePoints, // Stored in image coordinates
        label: activeLabel,
        color,
        visible: true,
      };
      onAddAnnotation(newAnn);
      resetDrawingState();
    }
  };

  const handleDoubleClick = () => {
    if (activeTool === 'polygon' && isDrawing && currentImagePoints.length >= 3) {
      finishPolygon();
    }
  };

  function finishPolygon() {
    const color = activeColor || TOOL_COLORS[annotations.length % TOOL_COLORS.length];
    const newAnn: LocalAnnotation = {
      id: `ann-poly-${Date.now()}`,
      type: 'polygon',
      points: currentImagePoints, // Stored in image coordinates
      label: activeLabel,
      color,
      visible: true,
    };
    onAddAnnotation(newAnn);
    resetDrawingState();
  }

  function resetDrawingState() {
    setCurrentScreenPoints([]);
    setCurrentImagePoints([]);
    setCurrentCircleScreen(null);
    setIsDrawing(false);
  }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '400px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #edf5ed',
        overflow: 'hidden',
        ...style,
      }}
    >
      {isAiLoading && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(255, 255, 255, 0.75)',
            zIndex: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            color: '#7e22ce',
            backdropFilter: 'blur(3px)',
          }}
        >
          ✨ AI Segmenting Object...
        </div>
      )}

      {imageLoaded && displayDim.width > 0 ? (
        <canvas
          ref={canvasRef}
          width={displayDim.width}
          height={displayDim.height}
          style={{
            cursor: activeTool === 'select' ? 'default' : 'crosshair',
            borderRadius: '8px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onDoubleClick={handleDoubleClick}
        />
      ) : (
        <div style={{ color: '#94a3b8', fontSize: '0.9rem' }}>Loading canvas image...</div>
      )}
    </div>
  );
};
