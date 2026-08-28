import { request } from './api';
import { UserStats, UserHistoryItem, RewardTransaction } from '../types/user';

export const userService = {
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
