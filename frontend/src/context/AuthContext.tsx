import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User } from '../types/auth';
import { UserStats } from '../types/user';
import { userService } from '../services/userService';
import { authService } from '../services/authService';

interface AuthContextType {
  user: User;
  stats: UserStats;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isSyncing: boolean;
  isDbConnected: boolean;
  lastSyncedAt: Date | null;
  login: (email: string, pass: string) => Promise<void>;
  logout: () => void;
  updateStats: (newStats: Partial<UserStats>) => void;
  refreshStats: () => Promise<void>;
}

const DEFAULT_USER: User = {
  user_id: 'usr_keerthana_01',
  email: 'keerthana@zwm.eco',
  full_name: 'Keerthana H M',
  role: 'user',
  is_email_verified: true,
  reward_points: 320,
  image_count: 128,
  created_at: '2025-01-15T10:00:00Z',
};

const DEFAULT_STATS: UserStats = {
  total_uploads: 128,
  validated_images: 96,
  pending_images: 32,
  reward_points: 320,
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User>(() => {
    try {
      const savedUser = localStorage.getItem('zwm_user');
      if (savedUser && savedUser !== 'undefined' && savedUser !== 'null') {
        const parsed = JSON.parse(savedUser);
        if (parsed && typeof parsed === 'object' && parsed.email) return parsed;
      }
    } catch (e) {}
    return DEFAULT_USER;
  });

  const [stats, setStats] = useState<UserStats>(() => {
    try {
      const savedStats = localStorage.getItem('zwm_stats');
      if (savedStats && savedStats !== 'undefined' && savedStats !== 'null') {
        const parsed = JSON.parse(savedStats);
        if (parsed && typeof parsed === 'object') return parsed;
      }
    } catch (e) {}
    return DEFAULT_STATS;
  });

  const [token, setToken] = useState<string | null>(localStorage.getItem('zwm_token'));
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [isDbConnected, setIsDbConnected] = useState<boolean>(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(new Date());

  // Function to fetch real-time stats from database
  const refreshStats = useCallback(async () => {
    const currentToken = localStorage.getItem('zwm_token');
    if (!currentToken) return;

    setIsSyncing(true);
    try {
      const liveStats = await userService.getStats();
      if (liveStats && typeof liveStats.total_uploads === 'number') {
        setStats(liveStats);
        localStorage.setItem('zwm_stats', JSON.stringify(liveStats));
        setIsDbConnected(true);
        setLastSyncedAt(new Date());
      }
    } catch (err) {
      setIsDbConnected(false);
      setLastSyncedAt(new Date());
    } finally {
      setIsSyncing(false);
    }
  }, []);

  // Fetch on mount & setup real-time polling every 6 seconds when authenticated
  useEffect(() => {
    if (!token) return;

    refreshStats();

    authService.getProfile()
      .then((profile) => {
        setUser(profile);
        localStorage.setItem('zwm_user', JSON.stringify(profile));
      })
      .catch(() => {});

    const interval = setInterval(() => {
      refreshStats();
    }, 6000);

    return () => clearInterval(interval);
  }, [token, refreshStats]);

  const login = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const res = await authService.login(email, pass);
      localStorage.setItem('zwm_token', res.access_token);
      setToken(res.access_token);
      const profile = await authService.getProfile();
      setUser(profile);
      localStorage.setItem('zwm_user', JSON.stringify(profile));
      await refreshStats();
    } catch (err: any) {
      throw new Error(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    authService.logout();
    setToken(null);
    setUser(DEFAULT_USER);
    localStorage.removeItem('zwm_stats');
  };

  const updateStats = (newStats: Partial<UserStats>) => {
    setStats((prev) => {
      const updated = { ...prev, ...newStats };
      localStorage.setItem('zwm_stats', JSON.stringify(updated));
      return updated;
    });
    setLastSyncedAt(new Date());
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        stats,
        token,
        isAuthenticated: !!token,
        isLoading,
        isSyncing,
        isDbConnected,
        lastSyncedAt,
        login,
        logout,
        updateStats,
        refreshStats,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
