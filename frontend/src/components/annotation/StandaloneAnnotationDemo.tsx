import React, { useState } from 'react';
import {
  Square,
  Pentagon,
  Circle,
  Pencil,
  Sparkles,
  Undo2,
  Redo2,
  Trash2,
  Eye,
  EyeOff,
  RotateCcw,
} from 'lucide-react';
import { LocalAnnotationCanvas, AnnotationTool } from './LocalAnnotationCanvas';
import { useAnnotationState } from './useAnnotationState';
import { Point, LocalAnnotation } from './types';
import { annotationService } from '../../services/annotationService';

export interface StandaloneAnnotationDemoProps {
  imageSrc: string;
  imageId?: string;
  onSaveLocally?: (annotations: LocalAnnotation[]) => void;
}

export const StandaloneAnnotationDemo: React.FC<StandaloneAnnotationDemoProps> = ({
  imageSrc,
  imageId,
  onSaveLocally,
}) => {
  const [activeTool, setActiveTool] = useState<AnnotationTool>('ai_polygon');
  const [activeLabel, setActiveLabel] = useState<string>('Waste Item');

  const {
    annotations,
    addAnnotation,
    deleteAnnotation,
    clearAll,
    undo,
    redo,
    canUndo,
    canRedo,
    isVisible,
    toggleVisibility,
    selectedId,
    selectAnnotation,
  } = useAnnotationState([]);

  // AI Polygon Handler
  const handleAIClick = async (imagePt: Point): Promise<Point[] | null> => {
    if (!imageId && !imageSrc) return null;
    try {
      const res = await annotationService.getAIPolygonFromClick(
        imageId,
        imagePt.x,
        imagePt.y,
        0.25,
        imageId ? undefined : imageSrc
      );

      const rawPoints: any = res?.polygon?.points || res?.polygon || (res as any)?.points || (res as any)?.raw_polygon?.points;

      if (Array.isArray(rawPoints) && rawPoints.length >= 3) {
        return rawPoints.map((p: any) => {
          if (Array.isArray(p)) return { x: Number(p[0]), y: Number(p[1]) };
          return { x: Number(p.x), y: Number(p.y) };
        });
      }
    } catch (err) {
      console.error('AI Polygon click error:', err);
    }
    return null;
  };

  const tools: { id: AnnotationTool; label: string; icon: React.ReactNode; isAi?: boolean }[] = [
    { id: 'ai_polygon', label: 'AI Polygon Mode', icon: <Sparkles size={20} />, isAi: true },
    { id: 'rectangle', label: 'Rectangle', icon: <Square size={20} /> },
    { id: 'polygon', label: 'Polygon', icon: <Pentagon size={20} /> },
    { id: 'circle', label: 'Circle', icon: <Circle size={20} /> },
    { id: 'freehand', label: 'Freehand', icon: <Pencil size={20} /> },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '100%', height: '100%' }}>
      {/* Top Controls Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          border: '1px solid #edf5ed',
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        {/* Tool Selectors */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {tools.map((tool) => (
            <button
              key={tool.id}
              onClick={() => setActiveTool(tool.id)}
              title={tool.label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                borderRadius: '8px',
                border: activeTool === tool.id
                  ? (tool.isAi ? '2px solid #8b5cf6' : '2px solid #22c55e')
                  : '1px solid #e2e8f0',
                backgroundColor: activeTool === tool.id
                  ? (tool.isAi ? '#f3e8ff' : '#f0fdf4')
                  : '#ffffff',
                color: activeTool === tool.id
                  ? (tool.isAi ? '#7e22ce' : '#15803d')
                  : '#64748b',
                fontWeight: 600,
                fontSize: '0.88rem',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {tool.icon}
              <span>{tool.label}</span>
            </button>
          ))}
        </div>

        {/* Action Controls: Undo, Redo, Visibility, Clear */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={undo}
            disabled={!canUndo}
            title="Undo"
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: canUndo ? '#334155' : '#cbd5e1',
              cursor: canUndo ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <Undo2 size={18} />
          </button>

          <button
            onClick={redo}
            disabled={!canRedo}
            title="Redo"
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: canRedo ? '#334155' : '#cbd5e1',
              cursor: canRedo ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <Redo2 size={18} />
          </button>

          <button
            onClick={toggleVisibility}
            title={isVisible ? 'Hide Annotations' : 'Show Annotations'}
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              backgroundColor: isVisible ? '#f8fafc' : '#fef2f2',
              color: isVisible ? '#334155' : '#ef4444',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontWeight: 600,
              fontSize: '0.85rem',
            }}
          >
            {isVisible ? <Eye size={18} /> : <EyeOff size={18} />}
            {isVisible ? 'Visible' : 'Hidden'}
          </button>

          <button
            onClick={clearAll}
            disabled={annotations.length === 0}
            title="Clear All Annotations"
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #fecaca',
              backgroundColor: '#fff5f5',
              color: annotations.length > 0 ? '#dc2626' : '#cbd5e1',
              cursor: annotations.length > 0 ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontWeight: 600,
              fontSize: '0.85rem',
            }}
          >
            <RotateCcw size={16} />
            Clear
          </button>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div style={{ display: 'flex', gap: '16px', flex: 1, minHeight: 0 }}>
        {/* Canvas Component */}
        <LocalAnnotationCanvas
          imageSrc={imageSrc}
          activeTool={activeTool}
          annotations={annotations}
          onAddAnnotation={addAnnotation}
          onSelectAnnotation={selectAnnotation}
          onAIClick={handleAIClick}
          selectedId={selectedId}
          isVisible={isVisible}
          activeLabel={activeLabel}
          style={{ flex: 1 }}
        />

        {/* Sidebar: Annotations List */}
        <div
          style={{
            width: '260px',
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: '1px solid #edf5ed',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569' }}>Active Label</label>
            <input
              type="text"
              value={activeLabel}
              onChange={(e) => setActiveLabel(e.target.value)}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            />
          </div>

          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#1e293b', margin: 0 }}>
            Local Shapes ({annotations.length})
          </h4>

          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {annotations.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '24px 8px', color: '#94a3b8', fontSize: '0.82rem' }}>
                No annotations drawn yet. Draw on the canvas using tools above.
              </div>
            ) : (
              annotations.map((ann) => (
                <div
                  key={ann.id}
                  onClick={() => selectAnnotation(ann.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    border: selectedId === ann.id ? `2px solid ${ann.color || '#22c55e'}` : '1px solid #e2e8f0',
                    backgroundColor: selectedId === ann.id ? (ann.color ? ann.color + '15' : '#f0fdf4') : '#ffffff',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: ann.color || '#22c55e', textTransform: 'uppercase' }}>
                      {ann.aiGenerated && '✨ '}
                      {ann.type}
                    </span>
                    <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#334155' }}>
                      {ann.label || 'Object'}
                    </span>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteAnnotation(ann.id);
                    }}
                    title="Delete shape"
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#ef4444',
                      cursor: 'pointer',
                      padding: '4px',
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))
            )}
          </div>

          {onSaveLocally && (
            <button
              onClick={() => onSaveLocally(annotations)}
              disabled={annotations.length === 0}
              style={{
                padding: '10px',
                borderRadius: '8px',
                border: 'none',
                backgroundColor: annotations.length > 0 ? '#16a34a' : '#e2e8f0',
                color: annotations.length > 0 ? '#ffffff' : '#94a3b8',
                fontWeight: 700,
                fontSize: '0.88rem',
                cursor: annotations.length > 0 ? 'pointer' : 'not-allowed',
              }}
            >
              Export Local Data ({annotations.length})
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
