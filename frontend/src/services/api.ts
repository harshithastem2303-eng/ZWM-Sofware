const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

/**
 * Generic request helper for User API endpoints
 */
export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token =
    localStorage.getItem('zwm_token') ||
    localStorage.getItem('zwm_admin_token') ||
    sessionStorage.getItem('zwm_admin_token');

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Set default JSON Content-Type unless it is FormData
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const url = `${API_BASE}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('zwm_token');
        localStorage.removeItem('zwm_user');
        localStorage.removeItem('zwm_stats');
      }
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
    }

    return (await response.json()) as T;
  } catch (err: any) {
    console.warn(`[API] Request to ${endpoint} failed:`, err.message);
    throw err;
  }
}

/**
 * Admin API Functions & Token Management
 */
export const storeToken = (token: string, role: string, rememberMe?: boolean) => {
  const storage = rememberMe ? localStorage : sessionStorage;
  storage.setItem('zwm_admin_token', token);
  storage.setItem('zwm_admin_role', role);
};

export const getToken = (): string | null => {
  return localStorage.getItem('zwm_admin_token') || sessionStorage.getItem('zwm_admin_token');
};

export const getRole = (): string | null => {
  return localStorage.getItem('zwm_admin_role') || sessionStorage.getItem('zwm_admin_role');
};

export const clearToken = () => {
  localStorage.removeItem('zwm_admin_token');
  localStorage.removeItem('zwm_admin_role');
  sessionStorage.removeItem('zwm_admin_token');
  sessionStorage.removeItem('zwm_admin_role');
};

export const isAuthenticated = (): boolean => {
  const token = getToken();
  const role = getRole();
  return !!token && role === 'admin';
};

export const adminLogin = async (email: string, password: string) => {
  const response = await fetch(`${API_BASE_URL}/admin/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to login';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const fetchAnalyticsDetails = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/analytics/details`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearToken();
    }
    throw new Error('Failed to fetch analytics details');
  }

  return await response.json();
};

export const fetchUsersList = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/users`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearToken();
    }
    throw new Error('Failed to fetch users list');
  }

  return await response.json();
};

export const createNewAdmin = async (email: string, password: string, confirmPassword?: string, role: string = 'Super Admin') => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/create`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ email, password, confirm_password: confirmPassword, role }),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to create admin';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const fetchActiveCategories = async () => {
  const response = await fetch(`${API_BASE_URL}/categories/active`, {
    method: 'GET',
  });

  if (!response.ok) {
    throw new Error('Failed to fetch active categories');
  }

  return await response.json();
};

export const fetchCategoriesList = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/categories`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearToken();
    }
    throw new Error('Failed to fetch categories list');
  }

  return await response.json();
};

export const createCategory = async (className: string, classCode: string | number, description?: string, isActive = true) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/categories`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      class_name: className,
      class_code: Number(classCode),
      description: description || '',
      is_active: isActive
    }),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to create category';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const updateCategory = async (categoryId: number, updateData: { class_name?: string; class_code?: number; description?: string; is_active?: boolean }) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/categories/${categoryId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(updateData),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to update category';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const deleteCategory = async (categoryId: number) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/categories/${categoryId}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    let errorMessage = 'Failed to delete category';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};


export const fetchValidationQueue = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/validation-queue`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch validation queue');
  }

  return await response.json();
};

export const validateImageAction = async (imageId: string | number, action: string) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/images/${imageId}/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ action }),
  });

  if (!response.ok) {
    let errorMessage = `Failed to ${action} image`;
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const fetchSystemHealth = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/health/system`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch system health status');
  }

  return await response.json();
};

export const fetchRecentActivities = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/activities`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch recent activities');
  }

  return await response.json();
};

export const triggerTrainingJob = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/ml/train`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    let errorMessage = 'Failed to trigger training job';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const fetchTrainingJobs = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/ml/jobs`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch training jobs list');
  }

  return await response.json();
};

export const fetchActiveModel = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/ml/models/active`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error('Failed to fetch active model');
  }

  return await response.json();
};

export const getImageUrl = (imageId: string | number) => {
  return `${API_BASE_URL}/images/${imageId}/file`;
};

export const fetchSystemSettings = async () => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/settings`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch system settings');
  }

  return await response.json();
};

export const updateSystemSettings = async (settingsData: any) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/settings`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settingsData),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to update settings';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

