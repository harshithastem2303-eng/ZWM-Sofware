import { request } from './api';
import { User, LoginResponse } from '../types/auth';

export const authService = {
  async login(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async register(email: string, password: string, fullName: string): Promise<{ message: string }> {
    return request<{ message: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
  },

  async verifyEmail(token: string): Promise<{ message: string }> {
    return request<{ message: string }>('/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  },

  async getProfile(): Promise<User> {
    return request<User>('/user/profile');
  },

  logout(): void {
    localStorage.removeItem('zwm_token');
    localStorage.removeItem('zwm_user');
  },
};
