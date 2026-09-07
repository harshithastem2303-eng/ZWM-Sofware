import { request } from './api';
import { UserStats, UserHistoryItem, RewardTransaction } from '../types/user';

export interface UserDashboardData {
  user: {
    id: string;
    email: string;
    full_name: string;
  };
  stats: {
    total_submissions: number;
    points: number;
    rank: number;
  };
  recent_submissions: Array<{
    id: string;
    filename: string;
    status: string;
    is_validated: boolean;
    credits_awarded: number;
    uploaded_at: string | null;
  }>;
}

export const userService = {
  async getDashboard(): Promise<UserDashboardData> {
    return request<UserDashboardData>('/users/me/dashboard');
  },

  async getStats(): Promise<UserStats> {
    return request<UserStats>('/user/stats');
  },

  async getHistory(): Promise<{ history: UserHistoryItem[] }> {
    return request<{ history: UserHistoryItem[] }>('/user/history');
  },

  async getRewards(): Promise<{ reward_points: number; total_images_contributed: number }> {
    return request<{ reward_points: number; total_images_contributed: number }>('/user/rewards');
  },

  async getRewardHistory(): Promise<{ history: RewardTransaction[] }> {
    return request<{ history: RewardTransaction[] }>('/user/rewards/history');
  },
};
