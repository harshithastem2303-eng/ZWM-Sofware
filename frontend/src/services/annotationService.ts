import { request } from './api';

export interface Point {
  x: number;
  y: number;
}

export interface AIPolygonResult {
  points: Point[];
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface AIPolygonClickResponse {
  status: string;
  polygon: AIPolygonResult;
  x: number;
  y: number;
}

export interface AISegmentResponse {
  status: string;
  count: number;
  polygons: AIPolygonResult[];
}

export const annotationService = {
  /**
   * Request AI polygon auto-segmentation at canvas click coordinates (x, y).
   */
  async getAIPolygonFromClick(
    imageId?: string,
    x?: number,
    y?: number,
    conf = 0.25,
    imageB64?: string
  ): Promise<AIPolygonClickResponse> {
    return request<AIPolygonClickResponse>('/ai/polygon-click', {
      method: 'POST',
      body: JSON.stringify({
        image_id: imageId || undefined,
        image: imageB64 || undefined,
        x: x ? Math.round(x) : 0,
        y: y ? Math.round(y) : 0,
        conf,
      }),
    });
  },

  /**
   * Request full image AI auto-segmentation for all objects in the image.
   */
  async segmentImageAI(
    imageId: string,
    conf = 0.25
  ): Promise<AISegmentResponse> {
    return request<AISegmentResponse>('/ai/segment', {
      method: 'POST',
      body: JSON.stringify({
        image_id: imageId,
        conf,
      }),
    });
  },
};
