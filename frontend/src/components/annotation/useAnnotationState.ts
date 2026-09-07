import { useState, useCallback } from 'react';
import { LocalAnnotation } from './types';

export function useAnnotationState(initialAnnotations: LocalAnnotation[] = []) {
  const [annotations, setAnnotations] = useState<LocalAnnotation[]>(initialAnnotations);
  const [history, setHistory] = useState<LocalAnnotation[][]>([initialAnnotations]);
  const [historyIndex, setHistoryIndex] = useState<number>(0);
  const [isVisible, setIsVisible] = useState<boolean>(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const pushState = useCallback((newAnnotations: LocalAnnotation[]) => {
    setHistory((prev) => {
      const updated = prev.slice(0, historyIndex + 1);
      return [...updated, newAnnotations];
    });
    setHistoryIndex((prev) => prev + 1);
    setAnnotations(newAnnotations);
  }, [historyIndex]);

  const addAnnotation = useCallback(
    (ann: LocalAnnotation) => {
      const updated = [...annotations, { ...ann, visible: ann.visible ?? true }];
      pushState(updated);
    },
    [annotations, pushState]
  );

  const deleteAnnotation = useCallback(
    (id: string) => {
      const updated = annotations.filter((a) => a.id !== id);
      if (selectedId === id) setSelectedId(null);
      pushState(updated);
    },
    [annotations, selectedId, pushState]
  );

  const clearAll = useCallback(() => {
    setSelectedId(null);
    pushState([]);
  }, [pushState]);

  const undo = useCallback(() => {
    if (historyIndex > 0) {
      const nextIndex = historyIndex - 1;
      setHistoryIndex(nextIndex);
      setAnnotations(history[nextIndex]);
    }
  }, [historyIndex, history]);

  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const nextIndex = historyIndex + 1;
      setHistoryIndex(nextIndex);
      setAnnotations(history[nextIndex]);
    }
  }, [historyIndex, history]);

  const toggleVisibility = useCallback(() => {
    setIsVisible((prev) => !prev);
  }, []);

  const selectAnnotation = useCallback((id: string | null) => {
    setSelectedId(id);
  }, []);

  return {
    annotations,
    setAnnotations,
    addAnnotation,
    deleteAnnotation,
    clearAll,
    undo,
    redo,
    canUndo: historyIndex > 0,
    canRedo: historyIndex < history.length - 1,
    isVisible,
    toggleVisibility,
    selectedId,
    selectAnnotation,
  };
}
