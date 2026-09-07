/**
 * Standalone Local Annotation Types
 */

export type AnnotationType =
  | 'rectangle'
  | 'polygon'
  | 'circle'
  | 'freehand'
  | 'ai_polygon';

export interface Point {
  x: number;
  y: number;
}

export interface CircleData {
  cx: number;
  cy: number;
  r: number;
}

export interface LocalAnnotation {
  id: string;
  type: AnnotationType;
  points?: Point[];
  circle?: CircleData;
  label?: string;
  color?: string;
  aiGenerated?: boolean;
  visible?: boolean;
}

export interface Dimensions {
  width: number;
  height: number;
}

export interface ImageDimensions {
  display: Dimensions;
  natural: Dimensions;
}
