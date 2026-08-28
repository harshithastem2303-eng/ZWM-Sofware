export interface User {
  user_id: string;
  email: string;
  full_name?: string;
  role: string;
  is_email_verified: boolean;
  reward_points?: number;
  image_count?: number;
  created_at?: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface LoginResponse {
  message: string;
  access_token: string;
  refresh_token: string;
  user_id: string;
  role: string;
}
