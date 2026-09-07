import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ArrowLeft,
  Square,
  Pentagon,
  Circle,
  Pencil,
  Sparkles,
  Trash2,
  Save,
  Undo2,
  Layers,
  Wand2,
  Loader2,
  X,
  Tag,
  Check,
} from 'lucide-react';
import { TopBar } from '../../components/dashboard/TopBar';
import { useAuth } from '../../context/AuthContext';
import { request, fetchActiveCategories } from '../../services/api';
import { annotationService } from '../../services/annotationService';

type AnnotationTool = 'rectangle' | 'polygon' | 'circle' | 'freehand' | 'ai_polygon' | 'select';

interface Point {
  x: number;
  y: number;
}

interface AnnotationShape {
  id: string;
  type: AnnotationTool;
  points: Point[];
  label: string;
  color: string;
  categoryId?: number;
  saved?: boolean;
}

export interface ActiveCategory {
  id: number;
  category_id: number;
  name: string;
  class_name: string;
  code: number;
  description?: string;
  is_active: boolean;
  validated_count?: number;
}

const TOOL_COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

export const AnnotationPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { refreshStats } = useAuth();

  const { imageId, previewUrl: passedPreviewUrl } = (location.state || {}) as {
    imageId?: string;
    previewUrl?: string;
  };

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const [activeTool, setActiveTool] = useState<AnnotationTool>('ai_polygon');
  const [annotations, setAnnotations] = useState<AnnotationShape[]>([]);
  const [currentPoints, setCurrentPoints] = useState<Point[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(passedPreviewUrl || null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imgDimensions, setImgDimensions] = useState({ width: 0, height: 0, naturalWidth: 0, naturalHeight: 0 });
  const [saving, setSaving] = useState(false);
  const [aiSegmenting, setAiSegmenting] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Category Selection Prompt Modal state
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [pendingAnn, setPendingAnn] = useState<AnnotationShape | null>(null);
  const [selectedCatIdForPrompt, setSelectedCatIdForPrompt] = useState<number | null>(null);

  // Categories list
  const [categories, setCategories] = useState<ActiveCategory[]>([]);
  const [loadingCategories, setLoadingCategories] = useState<boolean>(true);
  const [activeCategoryId, setActiveCategoryId] = useState<number | null>(null);

  // SaaS UI Floating Panels State
  const [showLayersPanel, setShowLayersPanel] = useState<boolean>(true);
  const [zoomLevel, setZoomLevel] = useState<number>(100);

  const handleDeleteShape = (id: string) => {
    setAnnotations((prev) => prev.filter((a) => a.id !== id));
  };

  // Fetch active categories on mount
  useEffect(() => {
    let isMounted = true;
    const loadCategories = async () => {
      setLoadingCategories(true);
      try {
        const res = await fetchActiveCategories();
        const cats: ActiveCategory[] = res.categories || [];
        if (isMounted) {
          setCategories(cats);
          if (cats.length > 0) {
            const firstId = cats[0].category_id || cats[0].id;
            setActiveCategoryId(firstId);
            setSelectedCatIdForPrompt(firstId);
          }
        }
      } catch (err: any) {
        console.error('Failed to load active classes', err);
      } finally {
        if (isMounted) {
          setLoadingCategories(false);
        }
      }
    };
    loadCategories();
    return () => {
      isMounted = false;
    };
  }, []);

  // Load the image from backend if no passedPreviewUrl
  useEffect(() => {
    if (!imageId) {
      navigate('/dashboard/upload');
      return;
    }
    if (!passedPreviewUrl && imageId) {
      const token = localStorage.getItem('zwm_token');
      if (token) {
        const apiBase = import.meta.env.VITE_API_BASE_URL || '/api';
        setImageUrl(`${apiBase}/images/${imageId}/file?token=${token}`);
      }
    }
  }, [imageId, passedPreviewUrl, navigate]);

  // Load image and draw on canvas
  useEffect(() => {
    if (!imageUrl) return;

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      setImageLoaded(true);

      const container = containerRef.current;
      if (!container) return;

      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight || 600;
      const scale = Math.min(containerWidth / img.naturalWidth, containerHeight / img.naturalHeight, 1);
      const displayW = img.naturalWidth * scale;
      const displayH = img.naturalHeight * scale;

      setImgDimensions({
        width: displayW,
        height: displayH,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight,
      });
    };
    img.onerror = () => {
      setErrorMessage('Failed to load image. Please go back and re-upload.');
    };
    img.src = imageUrl;
  }, [imageUrl]);

  // Redraw canvas whenever annotations or current drawing changes
  const redrawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !imageLoaded) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    // Draw saved annotations
    annotations.forEach((ann) => {
      drawAnnotation(ctx, ann);
    });

    // Draw current in-progress annotation
    if (currentPoints.length > 0) {
      const color = TOOL_COLORS[annotations.length % TOOL_COLORS.length];
      drawInProgress(ctx, activeTool, currentPoints, color);
    }
  }, [annotations, currentPoints, activeTool, imageLoaded]);

  useEffect(() => {
    redrawCanvas();
  }, [redrawCanvas]);

  function drawAnnotation(ctx: CanvasRenderingContext2D, ann: AnnotationShape) {
    ctx.save();
    ctx.strokeStyle = ann.color;
    ctx.lineWidth = 2.5;
    ctx.fillStyle = ann.color + '25';

    if (ann.type === 'rectangle' && ann.points.length >= 2) {
      const [p1, p2] = ann.points;
      const x = Math.min(p1.x, p2.x);
      const y = Math.min(p1.y, p2.y);
      const w = Math.abs(p2.x - p1.x);
      const h = Math.abs(p2.y - p1.y);
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
    } else if (ann.type === 'circle' && ann.points.length >= 2) {
      const [center, edge] = ann.points;
      const r = Math.sqrt(Math.pow(edge.x - center.x, 2) + Math.pow(edge.y - center.y, 2));
      ctx.beginPath();
      ctx.arc(center.x, center.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else if ((ann.type === 'polygon' || ann.type === 'freehand' || ann.type === 'ai_polygon') && ann.points.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(ann.points[0].x, ann.points[0].y);
      for (let i = 1; i < ann.points.length; i++) {
        ctx.lineTo(ann.points[i].x, ann.points[i].y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Draw vertex dots for polygons
      ann.points.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fillStyle = ann.color;
        ctx.fill();
      });
    }

    // Draw label tag above shape
    if (ann.points.length >= 1) {
      const labelX = ann.points[0].x;
      const labelY = ann.points[0].y - 6;
      ctx.font = 'bold 12px Inter, sans-serif';
      const text = `${ann.label}`;
      const metrics = ctx.measureText(text);
      ctx.fillStyle = ann.color;
      ctx.fillRect(labelX - 2, labelY - 14, metrics.width + 8, 18);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(text, labelX + 2, labelY);
    }

    ctx.restore();
  }

  function drawInProgress(ctx: CanvasRenderingContext2D, tool: AnnotationTool, points: Point[], color: string) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.fillStyle = color + '15';

    if (tool === 'rectangle' && points.length >= 2) {
      const [p1, p2] = points;
      const x = Math.min(p1.x, p2.x);
      const y = Math.min(p1.y, p2.y);
      const w = Math.abs(p2.x - p1.x);
      const h = Math.abs(p2.y - p1.y);
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
    } else if (tool === 'circle' && points.length >= 2) {
      const [center, edge] = points;
      const r = Math.sqrt(Math.pow(edge.x - center.x, 2) + Math.pow(edge.y - center.y, 2));
      ctx.beginPath();
      ctx.arc(center.x, center.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else if (tool === 'freehand' && points.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y);
      }
      ctx.stroke();
    } else if (tool === 'polygon' && points.length >= 1) {
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y);
      }
      ctx.stroke();

      // Vertex dots
      points.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      });
    }

    ctx.restore();
  }

  function getCanvasCoords(e: React.MouseEvent): Point {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    if (activeTool === 'select' || aiSegmenting) return;
    const pt = getCanvasCoords(e);

    if (activeTool === 'ai_polygon') {
      handleAIClickSegmentation(pt);
      return;
    }

    if (activeTool === 'rectangle' || activeTool === 'circle') {
      setCurrentPoints([pt]);
      setIsDrawing(true);
    } else if (activeTool === 'freehand') {
      setCurrentPoints([pt]);
      setIsDrawing(true);
    } else if (activeTool === 'polygon') {
      setCurrentPoints(prev => [...prev, pt]);
      if (!isDrawing) setIsDrawing(true);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDrawing || activeTool === 'ai_polygon') return;
    const pt = getCanvasCoords(e);

    if (activeTool === 'rectangle' || activeTool === 'circle') {
      setCurrentPoints(prev => [prev[0], pt]);
    } else if (activeTool === 'freehand') {
      setCurrentPoints(prev => [...prev, pt]);
    }
  };

  const handleMouseUp = (e: React.MouseEvent) => {
    if (!isDrawing || activeTool === 'ai_polygon') return;

    if (activeTool === 'rectangle' || activeTool === 'circle') {
      const pt = getCanvasCoords(e);
      const finalPoints = [currentPoints[0], pt];
      finishAnnotation(activeTool, finalPoints);
    } else if (activeTool === 'freehand') {
      finishAnnotation('freehand', currentPoints);
    }
  };

  const handleDoubleClick = () => {
    if (activeTool === 'polygon' && isDrawing && currentPoints.length >= 3) {
      finishAnnotation('polygon', currentPoints);
    }
  };

  // AI Click-to-Segment Handler
  const handleAIClickSegmentation = async (pt: Point) => {
    if (!imageId || aiSegmenting) return;

    setAiSegmenting(true);
    setErrorMessage(null);
    setSavedMessage(null);

    try {
      // Scale display canvas point to native image resolution
      const scaleX = imgDimensions.naturalWidth / imgDimensions.width;
      const scaleY = imgDimensions.naturalHeight / imgDimensions.height;
      const nativeX = Math.round(pt.x * scaleX);
      const nativeY = Math.round(pt.y * scaleY);

      const res = await annotationService.getAIPolygonFromClick(imageId, nativeX, nativeY);

      // Support array of points [{x, y}] or object {points: [...]}
      const pointsList: Point[] = Array.isArray(res?.polygon)
        ? (res.polygon as any)
        : (res?.polygon?.points || res?.raw_polygon?.points || []);

      if (pointsList && pointsList.length >= 3) {
        // Map native polygon points back to canvas display coordinates
        const invScaleX = imgDimensions.width / imgDimensions.naturalWidth;
        const invScaleY = imgDimensions.height / imgDimensions.naturalHeight;

        const displayPoints: Point[] = pointsList.map(p => ({
          x: Math.round(p.x * invScaleX),
          y: Math.round(p.y * invScaleY),
        }));

        const color = TOOL_COLORS[annotations.length % TOOL_COLORS.length];
        const currentCat = categories.find(c => (c.category_id || c.id) === activeCategoryId);

        const newAnn: AnnotationShape = {
          id: `ann-ai-${Date.now()}`,
          type: 'polygon',
          points: displayPoints,
          label: currentCat ? (currentCat.class_name || currentCat.name) : (res?.raw_polygon?.class_name || 'AI Object'),
          color,
          categoryId: activeCategoryId || undefined,
        };

        setAnnotations(prev => [...prev, newAnn]);
        setPendingAnn(newAnn);
        setShowCategoryModal(true);
        setSavedMessage('✨ AI Polygon boundary detected successfully! Please confirm class / category below.');
      } else {
        setErrorMessage('AI could not isolate object boundary at click point. Try clicking inside the object area.');
      }
    } catch (err: any) {
      console.error('AI Segmentation Click Error:', err);
      setErrorMessage(err.message || 'AI Segmentation request failed.');
    } finally {
      setAiSegmenting(false);
    }
  };

  // AI Full Image Auto-Segment Handler
  const handleAISegmentAll = async () => {
    if (!imageId || aiSegmenting) return;
    setAiSegmenting(true);
    setErrorMessage(null);
    setSavedMessage(null);

    try {
      const res = await annotationService.segmentImageAI(imageId);
      if (res && res.polygons && res.polygons.length > 0) {
        const invScaleX = imgDimensions.width / imgDimensions.naturalWidth;
        const invScaleY = imgDimensions.height / imgDimensions.naturalHeight;
        const currentCat = categories.find(c => (c.category_id || c.id) === activeCategoryId);

        const newAnns: AnnotationShape[] = res.polygons.map((poly, idx) => {
          const color = TOOL_COLORS[(annotations.length + idx) % TOOL_COLORS.length];
          const displayPoints = poly.points.map(p => ({
            x: Math.round(p.x * invScaleX),
            y: Math.round(p.y * invScaleY),
          }));
          return {
            id: `ann-ai-auto-${Date.now()}-${idx}`,
            type: 'polygon',
            points: displayPoints,
            label: currentCat ? (currentCat.class_name || currentCat.name) : (poly.class_name || 'Object'),
            color,
            categoryId: activeCategoryId || undefined,
          };
        });

        setAnnotations(prev => [...prev, ...newAnns]);
        setSavedMessage(`✨ AI detected ${newAnns.length} object boundary polygons!`);
      } else {
        setErrorMessage('AI segmentation found no clear object boundaries in this image.');
      }
    } catch (err: any) {
      console.error('AI Full Segment Error:', err);
      setErrorMessage(err.message || 'AI full segmentation failed.');
    } finally {
      setAiSegmenting(false);
    }
  };

  function finishAnnotation(type: AnnotationTool, points: Point[]) {
    const color = TOOL_COLORS[annotations.length % TOOL_COLORS.length];
    const currentCat = categories.find(c => (c.category_id || c.id) === activeCategoryId);
    const newAnn: AnnotationShape = {
      id: `ann-${Date.now()}`,
      type,
      points,
      label: currentCat ? (currentCat.class_name || currentCat.name) : 'Object',
      color,
      categoryId: activeCategoryId || undefined,
    };
    setAnnotations(prev => [...prev, newAnn]);
    setCurrentPoints([]);
    setIsDrawing(false);
  }

  const handleUndo = () => {
    setAnnotations(prev => prev.slice(0, -1));
    setCurrentPoints([]);
    setIsDrawing(false);
  };

  const handleDeleteAnnotation = (id: string) => {
    setAnnotations(prev => prev.filter(a => a.id !== id));
  };

  const handleSave = async () => {
    if (annotations.length === 0) {
      setErrorMessage('Please draw or segment at least one object before saving.');
      return;
    }

    // Check if all annotations have a valid category class selected
    const missingClass = annotations.some(a => !a.categoryId);
    if (missingClass) {
      setErrorMessage('Please select a waste category/class for all annotations.');
      return;
    }

    setSaving(true);
    setErrorMessage(null);
    setSavedMessage(null);

    try {
      // Save each annotation to the backend database
      for (const ann of annotations) {
        if (ann.saved) continue;

        // Convert canvas scale back to native image dimensions
        const scaleX = imgDimensions.naturalWidth / imgDimensions.width;
        const scaleY = imgDimensions.naturalHeight / imgDimensions.height;
        const nativePoints = ann.points.map(p => ({
          x: Math.round(p.x * scaleX),
          y: Math.round(p.y * scaleY),
        }));

        let labelData: any;
        if (ann.type === 'circle' && nativePoints.length >= 2) {
          const [center, edge] = nativePoints;
          const r = Math.round(Math.sqrt(Math.pow(edge.x - center.x, 2) + Math.pow(edge.y - center.y, 2)));
          labelData = { cx: center.x, cy: center.y, r };
        } else {
          labelData = { points: nativePoints };
        }

        await request('/annotations/', {
          method: 'POST',
          body: JSON.stringify({
            image_id: imageId,
            annotation_type: ann.type === 'ai_polygon' ? 'polygon' : ann.type,
            label_data: labelData,
            category_id: ann.categoryId,
            image_width: imgDimensions.naturalWidth,
            image_height: imgDimensions.naturalHeight,
            ai_generated: ann.id.includes('ai'),
          }),
        });

        ann.saved = true;
      }

      refreshStats();
      setSavedMessage('Annotations successfully saved! +15 points awarded. 🎉');

      // Auto redirect to user dashboard
      setTimeout(() => {
        navigate('/dashboard');
      }, 2000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to save annotations. Please try again.');
    } finally {
      setSaving(false);
    }
  };  const tools: { id: AnnotationTool; label: string; icon: React.ReactNode; isAi?: boolean }[] = [
    { id: 'ai_polygon', label: 'AI Polygon Mode', icon: <Sparkles size={17} />, isAi: true },
    { id: 'rectangle', label: 'Rectangle', icon: <Square size={17} /> },
    { id: 'polygon', label: 'Polygon', icon: <Pentagon size={17} /> },
    { id: 'circle', label: 'Circle', icon: <Circle size={17} /> },
    { id: 'freehand', label: 'Freehand', icon: <Pencil size={17} /> },
  ];

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 9999,
        backgroundColor: '#090d16',
        color: '#f8fafc',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        fontFamily: "var(--font-main), 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* Keyframe Micro-animations */}
      <style>{`
        @keyframes pulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.85); }
        }
        @keyframes aiGlow {
          0%, 100% { box-shadow: 0 0 25px rgba(139, 92, 246, 0.4), 0 0 10px rgba(139, 92, 246, 0.2); }
          50% { box-shadow: 0 0 35px rgba(168, 85, 247, 0.6), 0 0 15px rgba(168, 85, 247, 0.3); }
        }
        .tool-btn-hover:hover {
          transform: translateY(-1px);
          filter: brightness(1.1);
        }
      `}</style>

      {/* Top Header Bar */}
      <header
        style={{
          height: '66px',
          backgroundColor: 'rgba(15, 23, 42, 0.85)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          zIndex: 50,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            onClick={() => navigate('/dashboard/upload')}
            className="tool-btn-hover"
            style={{
              backgroundColor: 'rgba(51, 65, 85, 0.5)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '10px',
              padding: '8px 16px',
              color: '#f8fafc',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.2s ease',
            }}
          >
            <ArrowLeft size={16} /> Back to Upload
          </button>

          <div style={{ height: '24px', width: '1px', backgroundColor: 'rgba(255,255,255,0.1)' }} />

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                background: 'linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)',
                color: '#ffffff',
                fontSize: '0.72rem',
                fontWeight: 800,
                padding: '3px 9px',
                borderRadius: '6px',
                letterSpacing: '0.5px',
                textTransform: 'uppercase',
              }}
            >
              ZWM Studio v2.4
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2 style={{ margin: 0, fontSize: '1.08rem', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.01em' }}>
                Annotator Workspace
              </h2>
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: 'rgba(34, 197, 94, 0.12)',
                  border: '1px solid rgba(34, 197, 94, 0.25)',
                  color: '#4ade80',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '3px 10px',
                  borderRadius: '20px',
                }}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#22c55e',
                    animation: 'pulseDot 2s infinite',
                  }}
                />
                {annotations.length} shape(s)
              </span>
            </div>
          </div>
        </div>

        {/* Central Floating Tool Selector Bar with explicit names */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            backgroundColor: 'rgba(30, 41, 59, 0.85)',
            backdropFilter: 'blur(16px)',
            borderRadius: '32px',
            padding: '5px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            gap: '4px',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
          }}
        >
          {tools.map((tool) => {
            const isActive = activeTool === tool.id;
            return (
              <button
                key={tool.id}
                onClick={() => {
                  setActiveTool(tool.id);
                  setCurrentPoints([]);
                  setIsDrawing(false);
                }}
                className="tool-btn-hover"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 18px',
                  borderRadius: '24px',
                  border: 'none',
                  background: isActive
                    ? tool.isAi
                      ? 'linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)'
                      : 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                    : 'transparent',
                  color: isActive ? '#ffffff' : '#94a3b8',
                  fontWeight: isActive ? 700 : 500,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
                  boxShadow: isActive
                    ? tool.isAi
                      ? '0 4px 15px rgba(139, 92, 246, 0.4)'
                      : '0 4px 15px rgba(16, 185, 129, 0.35)'
                    : 'none',
                }}
              >
                {tool.icon}
                <span>{tool.label}</span>
              </button>
            );
          })}

          <div style={{ width: '1px', height: '22px', backgroundColor: 'rgba(255, 255, 255, 0.12)', margin: '0 4px' }} />

          <button
            onClick={handleUndo}
            title="Undo Last Action"
            className="tool-btn-hover"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              borderRadius: '24px',
              border: 'none',
              backgroundColor: 'transparent',
              color: '#94a3b8',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            <Undo2 size={16} />
            <span>Undo</span>
          </button>
        </div>

        {/* Header Action Right: Active Category Selector & Save Button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '0.82rem', color: '#94a3b8', fontWeight: 600 }}>Active Class:</span>
            <select
              value={activeCategoryId || ''}
              onChange={(e) => setActiveCategoryId(Number(e.target.value))}
              style={{
                backgroundColor: 'rgba(30, 41, 59, 0.9)',
                color: '#f8fafc',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '10px',
                padding: '7px 14px',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              {categories.map((cat) => (
                <option key={cat.id || cat.category_id} value={cat.category_id || cat.id}>
                  {cat.class_name || cat.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleSave}
            disabled={saving || annotations.length === 0}
            className="tool-btn-hover"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: annotations.length > 0
                ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                : 'rgba(51, 65, 85, 0.6)',
              color: '#ffffff',
              border: 'none',
              borderRadius: '10px',
              padding: '9px 22px',
              fontWeight: 700,
              fontSize: '0.9rem',
              cursor: annotations.length > 0 ? 'pointer' : 'not-allowed',
              boxShadow: annotations.length > 0 ? '0 4px 18px rgba(16, 185, 129, 0.35)' : 'none',
              transition: 'all 0.2s ease',
            }}
          >
            {saving ? (
              <>
                <Loader2 size={18} className="animate-spin" /> Saving...
              </>
            ) : (
              <>
                <Save size={18} /> Save & Earn Points
              </>
            )}
          </button>
        </div>
      </header>

      {/* Messages Banner */}
      {(savedMessage || errorMessage) && (
        <div
          style={{
            backgroundColor: savedMessage ? '#15803d' : '#b91c1c',
            color: '#ffffff',
            padding: '10px 24px',
            fontSize: '0.88rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
            zIndex: 40,
          }}
        >
          <span>{savedMessage || errorMessage}</span>
          <button
            onClick={() => {
              setSavedMessage(null);
              setErrorMessage(null);
            }}
            style={{ background: 'none', border: 'none', color: '#ffffff', cursor: 'pointer' }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Full-Screen Center Canvas Workspace */}
      <main
        ref={containerRef}
        style={{
          flex: 1,
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'radial-gradient(circle at 50% 35%, #1e1b4b 0%, #090d16 75%, #020617 100%)',
          overflow: 'hidden',
          padding: '16px',
        }}
      >
        {/* Floating AI Active Indicator */}
        {activeTool === 'ai_polygon' && (
          <div
            style={{
              position: 'absolute',
              top: '20px',
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 30,
              backgroundColor: 'rgba(139, 92, 246, 0.95)',
              backdropFilter: 'blur(12px)',
              color: '#ffffff',
              padding: '9px 24px',
              borderRadius: '30px',
              fontSize: '0.88rem',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              boxShadow: '0 8px 25px rgba(139, 92, 246, 0.4)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              pointerEvents: 'none',
              animation: 'aiGlow 3s infinite ease-in-out',
            }}
          >
            <Sparkles size={18} color="#f472b6" />
            AI Polygon Mode Active: Click any object on image to auto-segment
          </div>
        )}

        {/* AI Segmenting Loader Overlay */}
        {aiSegmenting && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundColor: 'rgba(9, 13, 22, 0.85)',
              backdropFilter: 'blur(6px)',
              zIndex: 40,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '14px',
            }}
          >
            <Loader2 size={48} className="animate-spin" color="#a855f7" style={{ animation: 'spin 1s linear infinite' }} />
            <span style={{ fontWeight: 800, color: '#f3e8ff', fontSize: '1.2rem', letterSpacing: '-0.01em' }}>
              AI Segmenting Object Contour... 🪄
            </span>
          </div>
        )}

        {/* Canvas Element */}
        {imageLoaded && imgDimensions.width > 0 ? (
          <canvas
            ref={canvasRef}
            width={imgDimensions.width}
            height={imgDimensions.height}
            style={{
              cursor: 'crosshair',
              borderRadius: '14px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              boxShadow: '0 25px 60px rgba(0, 0, 0, 0.8), 0 0 50px rgba(139, 92, 246, 0.15)',
              backgroundColor: '#0f172a',
              transition: 'transform 0.2s ease-out',
              transform: `scale(${zoomLevel / 100})`,
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onDoubleClick={handleDoubleClick}
          />
        ) : (
          <div style={{ textAlign: 'center', color: '#94a3b8' }}>
            {errorMessage ? <p style={{ color: '#ef4444' }}>{errorMessage}</p> : <p>Loading canvas workspace...</p>}
          </div>
        )}

        {/* Floating Bottom-Left Zoom & Pan Overlay */}
        <div
          style={{
            position: 'absolute',
            bottom: '24px',
            left: '24px',
            zIndex: 30,
            display: 'flex',
            alignItems: 'center',
            backgroundColor: 'rgba(30, 41, 59, 0.85)',
            backdropFilter: 'blur(16px)',
            borderRadius: '12px',
            padding: '4px 8px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            gap: '8px',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
          }}
        >
          <button
            onClick={() => setZoomLevel((z) => Math.max(50, z - 15))}
            style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px', fontSize: '0.9rem', fontWeight: 700 }}
            title="Zoom Out"
          >
            -
          </button>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#f8fafc', minWidth: '40px', textAlign: 'center' }}>
            {zoomLevel}%
          </span>
          <button
            onClick={() => setZoomLevel((z) => Math.min(200, z + 15))}
            style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px', fontSize: '0.9rem', fontWeight: 700 }}
            title="Zoom In"
          >
            +
          </button>
          <div style={{ width: '1px', height: '18px', backgroundColor: 'rgba(255, 255, 255, 0.12)' }} />
          <button
            onClick={() => setZoomLevel(100)}
            style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', padding: '4px 8px', fontSize: '0.75rem', fontWeight: 700 }}
          >
            Reset
          </button>
        </div>

        {/* Floating Bottom-Right Collapsible Layers & Shortcuts Panel */}
        <div
          style={{
            position: 'absolute',
            bottom: '24px',
            right: '24px',
            zIndex: 30,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: '8px',
          }}
        >
          <div
            style={{
              backgroundColor: 'rgba(30, 41, 59, 0.85)',
              backdropFilter: 'blur(16px)',
              borderRadius: '16px',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
              width: '280px',
              overflow: 'hidden',
              transition: 'all 0.3s ease',
            }}
          >
            {/* Layers Header */}
            <div
              onClick={() => setShowLayersPanel(!showLayersPanel)}
              style={{
                padding: '12px 16px',
                backgroundColor: 'rgba(15, 23, 42, 0.6)',
                borderBottom: showLayersPanel ? '1px solid rgba(255, 255, 255, 0.08)' : 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Layers size={16} color="#8b5cf6" />
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>
                  Drawn Shapes ({annotations.length})
                </span>
              </div>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                {showLayersPanel ? '▼' : '▲'}
              </span>
            </div>

            {/* Layers Body */}
            {showLayersPanel && (
              <div style={{ maxHeight: '180px', overflowY: 'auto', padding: '8px' }}>
                {annotations.length === 0 ? (
                  <div style={{ padding: '12px', textAlign: 'center', fontSize: '0.78rem', color: '#64748b' }}>
                    No objects drawn yet. Select a tool above to begin annotating.
                  </div>
                ) : (
                  annotations.map((ann, idx) => (
                    <div
                      key={ann.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 10px',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(15, 23, 42, 0.4)',
                        marginBottom: '4px',
                        fontSize: '0.8rem',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: ann.color || '#22c55e',
                          }}
                        />
                        <span style={{ fontWeight: 600, color: '#f1f5f9' }}>{ann.label || `Shape #${idx + 1}`}</span>
                        <span style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'capitalize' }}>
                          ({ann.type.replace('_polygon', '')})
                        </span>
                      </div>
                      <button
                        onClick={() => handleDeleteShape(ann.id)}
                        style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: '2px' }}
                        title="Delete shape"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Interactive Category Selection Prompt Modal */}
      {showCategoryModal && pendingAnn && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            zIndex: 10000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: 'rgba(30, 41, 59, 0.95)',
              backdropFilter: 'blur(20px)',
              borderRadius: '20px',
              padding: '28px',
              width: '440px',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
              display: 'flex',
              flexDirection: 'column',
              gap: '18px',
              color: '#f8fafc',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  backgroundColor: 'rgba(168, 85, 247, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Tag color="#a855f7" size={22} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 800, color: '#f8fafc' }}>
                  Select Category for Object
                </h3>
                <p style={{ margin: 0, fontSize: '0.85rem', color: '#94a3b8', marginTop: '2px' }}>
                  Choose the waste item class label for the detected object:
                </p>
              </div>
            </div>

            <select
              value={selectedCatIdForPrompt || ''}
              onChange={(e) => setSelectedCatIdForPrompt(Number(e.target.value))}
              style={{
                padding: '12px 16px',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                backgroundColor: '#0f172a',
                color: '#f8fafc',
                fontSize: '0.95rem',
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              {categories.map((cat) => (
                <option key={cat.id || cat.category_id} value={cat.category_id || cat.id}>
                  {cat.class_name || cat.name}
                </option>
              ))}
            </select>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '6px' }}>
              <button
                onClick={() => {
                  setShowCategoryModal(false);
                  setPendingAnn(null);
                }}
                style={{
                  padding: '10px 18px',
                  borderRadius: '10px',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  backgroundColor: 'transparent',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                }}
              >
                Skip
              </button>
              <button
                onClick={() => {
                  if (selectedCatIdForPrompt && pendingAnn) {
                    const catObj = categories.find((c) => (c.category_id || c.id) === selectedCatIdForPrompt);
                    const catName = catObj ? catObj.class_name || catObj.name : 'Object';
                    setAnnotations((prev) =>
                      prev.map((a) =>
                        a.id === pendingAnn.id
                          ? { ...a, categoryId: selectedCatIdForPrompt, label: catName }
                          : a
                      )
                    );
                    setActiveCategoryId(selectedCatIdForPrompt);
                  }
                  setShowCategoryModal(false);
                  setPendingAnn(null);
                }}
                style={{
                  padding: '10px 22px',
                  borderRadius: '10px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)',
                  color: '#ffffff',
                  cursor: 'pointer',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  boxShadow: '0 4px 15px rgba(139, 92, 246, 0.4)',
                }}
              >
                <Check size={18} /> Confirm Category
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
