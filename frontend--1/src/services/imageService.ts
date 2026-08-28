import { request } from './api';
import { ImageRecord, UploadResponse } from '../types/image';

export const imageService = {
  async uploadImage(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    return request<UploadResponse>('/images/upload', {
      method: 'POST',
      body: formData,
    });
  },

  async listImages(skip = 0, limit = 50): Promise<{ images: ImageRecord[]; count: number }> {
    return request<{ images: ImageRecord[]; count: number }>(`/images/?skip=${skip}&limit=${limit}`);
  },

  async getImage(imageId: string): Promise<ImageRecord> {
    return request<ImageRecord>(`/images/${imageId}`);
  },

  async deleteImage(imageId: string): Promise<{ message: string }> {
    return request<{ message: string }>(`/images/${imageId}`, {
      method: 'DELETE',
    });
  },
};
