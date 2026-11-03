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
      throw new Error(errorData.error?.message || errorData.detail || errorData.message || `HTTP ${response.status}`);
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


// ---- Model approval, activation & rollback (Block A4, admin only) ----

const adminMlRequest = (path: string, method: string = 'GET', body?: any) =>
  adminRequest(`/ml${path}`, method, body);

const adminRequest = async (path: string, method: string = 'GET', body?: any) => {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (!response.ok) {
    let errorMessage = `Request failed (${response.status})`;
    try {
      const errData = await response.json();
      errorMessage = errData.error?.message || errData.detail || errorMessage;
    } catch (e) {}
    throw new Error(errorMessage);
  }

  return await response.json();
};

export const fetchModelCandidates = () => adminMlRequest('/candidates');

export const fetchCandidateApproval = (modelId: string) =>
  adminMlRequest(`/candidates/${encodeURIComponent(modelId)}/approval`);

export const approveCandidate = (modelId: string, evaluationId: string, reason?: string) =>
  adminMlRequest(`/candidates/${encodeURIComponent(modelId)}/approve`, 'POST', {
    evaluation_id: evaluationId,
    ...(reason ? { reason } : {}),
  });

export const rejectCandidate = (modelId: string, evaluationId: string, reason: string) =>
  adminMlRequest(`/candidates/${encodeURIComponent(modelId)}/reject`, 'POST', {
    evaluation_id: evaluationId,
    reason,
  });

export const activateModelVersion = (modelId: string, reason?: string) =>
  adminMlRequest(`/models/${encodeURIComponent(modelId)}/activate`, 'POST', reason ? { reason } : {});

export const fetchDeployments = () => adminMlRequest('/deployments');

export const fetchDeploymentEvents = () => adminMlRequest('/deployments/events');

export const rollbackDeployment = (reason: string, targetModelId?: string) =>
  adminMlRequest('/deployments/rollback', 'POST', {
    reason,
    ...(targetModelId ? { target_model_id: targetModelId } : {}),
  });

// ---- Administrator monitoring (Block A5, read-only) ----

const toQuery = (params: Record<string, any>) => {
  const q = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return q.length ? `?${q.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')}` : '';
};

export const fetchMonitoringSummary = () => adminMlRequest('/monitoring/summary');

export const fetchMonitoringTimeline = (params: { limit?: number; offset?: number; source?: string } = {}) =>
  adminMlRequest(`/monitoring/timeline${toQuery(params)}`);

export const fetchTrainingJobsPage = (params: { limit?: number; offset?: number; status?: string; trigger?: string } = {}) =>
  adminMlRequest(`/jobs${toQuery(params)}`);

export const fetchTrainingJobDetail = (jobId: string) => adminMlRequest(`/jobs/${encodeURIComponent(jobId)}`);

export const fetchEvaluationsPage = (params: { limit?: number; offset?: number; status?: string } = {}) =>
  adminMlRequest(`/evaluations${toQuery(params)}`);

export const fetchDeploymentsPage = (params: { limit?: number; offset?: number; kind?: string } = {}) =>
  adminMlRequest(`/deployments${toQuery(params)}`);

export const fetchApprovalsPage = (params: { limit?: number; offset?: number; decision?: string } = {}) =>
  adminMlRequest(`/approvals${toQuery(params)}`);


// ---- Prediction feedback (Block A6.2) ----
// Users report incorrect AI predictions; administrators approve or reject the reports.
// A decision never changes labels or training eligibility.

export type FeedbackType = 'incorrect_class' | 'incorrect_geometry' | 'missed_object' | 'false_detection' | 'other';

export interface FeedbackSubmission {
  feedback_type: FeedbackType;
  detection_index?: number;
  explanation?: string;
  suggested_category_id?: number;
  suggested_geometry?:
    | { type: 'bbox'; bbox: [number, number, number, number] }
    | { type: 'polygon'; points: { x: number; y: number }[] };
}

export const fetchPredictionsForImage = (imageId: string) =>
  request<any>(`/ml/predictions${toQuery({ image_id: imageId, limit: 20 })}`);

export const fetchPrediction = (predictionId: string) =>
  request<any>(`/ml/predictions/${encodeURIComponent(predictionId)}`);

export const submitPredictionFeedback = (predictionId: string, body: FeedbackSubmission) =>
  request<any>(`/ml/predictions/${encodeURIComponent(predictionId)}/feedback`, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const fetchMyFeedback = (params: { image_id?: string; status?: string; limit?: number; offset?: number } = {}) =>
  request<any>(`/ml/feedback${toQuery(params)}`);

export const fetchFeedbackQueue = (params: {
  status?: string; feedback_type?: string; submitted_from?: string; submitted_to?: string;
  order?: string; limit?: number; offset?: number;
} = {}) => adminMlRequest(`/feedback-review${toQuery(params)}`);

export const fetchFeedbackReview = (feedbackId: string) =>
  adminMlRequest(`/feedback-review/${encodeURIComponent(feedbackId)}`);

export const approveFeedback = (feedbackId: string, reason?: string) =>
  adminMlRequest(`/feedback-review/${encodeURIComponent(feedbackId)}/approve`, 'POST', reason ? { reason } : {});

export const rejectFeedback = (feedbackId: string, reason: string) =>
  adminMlRequest(`/feedback-review/${encodeURIComponent(feedbackId)}/reject`, 'POST', { reason });


// ---- Immutable label revisions (Block A6.3, administrator actions) ----
// A revision is a complete, immutable label state. Approved feedback becomes a draft
// revision; an independent administrator approves it; activation rewrites the image's
// annotations and label, which then still needs the A6.0 label review to be trainable.

const revisionRequest = (path: string, method: string = 'GET', body?: any) =>
  adminRequest(`/label-revisions${path}`, method, body);
const rid = (id: string) => encodeURIComponent(id);

export const fetchRevisionQueue = (params: {
  status?: string; image_id?: string; feedback_id?: string; source?: string; limit?: number; offset?: number;
} = {}) => revisionRequest(`/review-queue${toQuery(params)}`);

export const fetchImageRevisionsAdmin = (imageId: string) => revisionRequest(`/admin/image/${rid(imageId)}`);

export const fetchRevisionAdmin = (revisionId: string) => revisionRequest(`/admin/revision/${rid(revisionId)}`);

export const createRevisionFromFeedback = (
  feedbackId: string, body: { reason: string; target_object_key?: string; category_id?: number },
) => revisionRequest(`/from-feedback/${rid(feedbackId)}`, 'POST', body);

export const submitRevision = (revisionId: string) => revisionRequest(`/${rid(revisionId)}/submit`, 'POST');

export const approveRevision = (revisionId: string, reason?: string) =>
  revisionRequest(`/${rid(revisionId)}/approve`, 'POST', reason ? { reason } : {});

export const rejectRevision = (revisionId: string, reason: string) =>
  revisionRequest(`/${rid(revisionId)}/reject`, 'POST', { reason });

export const activateRevision = (revisionId: string) => revisionRequest(`/${rid(revisionId)}/activate`, 'POST');

export const restoreRevision = (revisionId: string, reason: string) =>
  revisionRequest(`/${rid(revisionId)}/restore`, 'POST', { reason });
