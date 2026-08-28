const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

/**
 * Store the JWT token securely.
 * If rememberMe is checked, we use localStorage to persist across browser sessions.
 * Otherwise, we use sessionStorage.
 */
export const storeToken = (token, role, rememberMe) => {
  const storage = rememberMe ? localStorage : sessionStorage;
  storage.setItem('zwm_admin_token', token);
  storage.setItem('zwm_admin_role', role);
};

export const getToken = () => {
  return localStorage.getItem('zwm_admin_token') || sessionStorage.getItem('zwm_admin_token');
};

export const getRole = () => {
  return localStorage.getItem('zwm_admin_role') || sessionStorage.getItem('zwm_admin_role');
};

export const clearToken = () => {
  localStorage.removeItem('zwm_admin_token');
  localStorage.removeItem('zwm_admin_role');
  sessionStorage.removeItem('zwm_admin_token');
  sessionStorage.removeItem('zwm_admin_role');
};

export const isAuthenticated = () => {
  const token = getToken();
  const role = getRole();
  return !!token && role === 'admin';
};

/**
 * Call the backend admin login API.
 */
export const adminLogin = async (email, password) => {
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
    } catch (e) {
      // Ignore parsing error
    }
    throw new Error(errorMessage);
  }

  return await response.json();
};

/**
 * Fetch detailed analytics for the dashboard.
 */
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

/**
 * Fetch list of all registered users.
 */
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

/**
 * Register a new admin inside the ZWM system.
 */
export const createNewAdmin = async (adminId, email, role) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/create`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ admin_id: adminId, email, role }),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to create admin';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {
      // Ignore parsing error
    }
    throw new Error(errorMessage);
  }

  return await response.json();
};

/**
 * Fetch all waste classification categories.
 */
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

/**
 * Create a new waste classification category.
 */
export const createCategory = async (className, classCode) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/admin/categories`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ class_name: className, class_code: classCode }),
  });

  if (!response.ok) {
    let errorMessage = 'Failed to create category';
    try {
      const errData = await response.json();
      errorMessage = errData.detail || errorMessage;
    } catch (e) {
      // Ignore parsing error
    }
    throw new Error(errorMessage);
  }

  return await response.json();
};


/**
 * Fetch validation queue of images awaiting review.
 */
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

/**
 * Approve or reject an image in the validation queue.
 */
export const validateImageAction = async (imageId, action) => {
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

/**
 * Fetch dynamic system health status.
 */
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

/**
 * Fetch recent activities stream.
 */
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

/**
 * Trigger retraining job.
 */
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

/**
 * Fetch all training jobs.
 */
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

/**
 * Fetch currently active ML model.
 */
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

/**
 * Helper to get the correct URL for an image file.
 */
export const getImageUrl = (imageId) => {
  return `${API_BASE_URL}/images/${imageId}/file`;
};


