export interface UserStats {
  total_uploads: number;
  validated_images: number;
  pending_images: number;
  reward_points: number;
}

export interface RewardTransaction {
  transaction_id: number;
  image_id?: string;
  points: number;
  description: string;
  created_at: string;
}

export interface UserHistoryItem {
  image_id: string;
  original_filename: string;
  status: string;
  is_validated: boolean;
  credits_awarded: number;
  uploaded_at: string;
}
