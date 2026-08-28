export interface ImageRecord {
  image_id: string;
  original_filename: string;
  status: 'uploaded' | 'rejected' | 'validated' | 'annotated' | 'approved';
  is_validated: boolean;
  credits_awarded?: number;
  uploaded_at: string;
  preview_url?: string;
  category?: string;
}

export interface UploadResponse {
  image_id: string;
  original_filename: string;
  status: string;
  validation: {
    valid: boolean;
    reason?: string;
    details?: Record<string, any>;
  };
}

export interface WasteCategory {
  id: string;
  name: string;
  code: number;
  icon: string;
  description: string;
  color: string;
}
