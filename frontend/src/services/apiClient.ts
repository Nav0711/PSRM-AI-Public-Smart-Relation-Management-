/**
 * API Client Service
 * Centralized API call management for P-CRM Frontend
 * 
 * Base URL: http://localhost:8000 (or configured via VITE_API_URL)
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  status: number;
}

class ApiClient {
  private getHeaders(): HeadersInit {
    const token = localStorage.getItem('auth_token');
    return {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
    };
  }

  private async request<T>(
    endpoint: string,
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH' = 'GET',
    body?: any
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${API_BASE_URL}${endpoint}`;
      const options: RequestInit = {
        method,
        headers: this.getHeaders(),
      };

      if (body) {
        options.body = JSON.stringify(body);
      }

      const response = await fetch(url, options);
      
      if (!response.ok) {
        let errorData: any = {};
        try {
          errorData = await response.json();
        } catch (e) {
          // Response wasn't JSON
        }
        throw new Error(errorData.detail || errorData.message || `API request failed with status ${response.status}`);
      }

      const data = await response.json();
      return { data, status: response.status };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error occurred';
      console.error(`[API] ${method} ${endpoint} failed:`, message);
      return {
        error: message,
        status: 0,
      };
    }
  }

  // ============ AUTH ENDPOINTS ============
  /**
   * POST /api/v1/auth/login
   * Login with phone or email
   */
  async login(username: string, password: string) {
    try {
      if (!username || !password) {
        throw new Error('Username and password are required');
      }

      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const url = `${API_BASE_URL}/api/v1/auth/login`;
      console.log(`[LOGIN] Attempting login for user: ${username} at ${url}`);

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: params.toString(),
      });

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        try {
          const errorData = await response.json();
          errorDetail = errorData.detail || errorData.message || errorDetail;
        } catch (e) {
          // Response wasn't JSON
        }
        throw new Error(`Login failed: ${errorDetail}`);
      }

      const data = await response.json();
      console.log('[LOGIN] Success:', { id: data.user?.id, role: data.user?.role });
      return data;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Network error or CORS issue';
      const isDnsError = message.includes('Failed to fetch') || message.includes('ERR_NAME_NOT_RESOLVED');
      
      console.error('[LOGIN] Error:', {
        message,
        isDnsError,
        apiUrl: API_BASE_URL,
        timestamp: new Date().toISOString(),
      });

      if (isDnsError) {
        throw new Error(`Connection Error: Could not resolve server at ${API_BASE_URL}. Please check your internet connection or DNS settings (e.g., try 8.8.8.8).`);
      }
      throw error;
    }
  }

  /**
   * POST /api/v1/auth/register
   * Register a new user
   */
  async register(userData: {
    phone: string;
    email: string;
    name: string;
    password: string;
    role: 'FieldWorker' | 'PA' | 'Politician';
    constituency_id?: string;
    ward_id?: string;
  }) {
    return this.request('/api/v1/auth/register', 'POST', userData);
  }

  // ============ COMPLAINTS ENDPOINTS ============
  /**
   * POST /api/v1/complaints
   * Create a new complaint
   */
  async createComplaint(complaintData: any) {
    return this.request('/api/v1/complaints', 'POST', complaintData);
  }

  /**
   * GET /api/v1/complaints
   * Get complaints (filtered by role on backend)
   */
  async getComplaints() {
    return this.request('/api/v1/complaints', 'GET');
  }

  /**
   * GET /api/v1/complaints/public
   * Get public complaints
   */
  async getPublicComplaints() {
    return this.request('/api/v1/complaints/public', 'GET');
  }

  /**
   * POST /api/v1/complaints/upload
   * Upload image
   */
  async uploadImage(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    
    // Custom fetch because request method assumes JSON body
    const response = await fetch(`${API_BASE_URL}/api/v1/complaints/upload`, {
      method: 'POST',
      headers: {
        ...(localStorage.getItem('auth_token') ? { 'Authorization': `Bearer ${localStorage.getItem('auth_token')}` } : {}),
      },
      body: formData,
    });
    
    if (!response.ok) {
       throw new Error('Upload failed');
    }
    return await response.json();
  }

  // End duplicate removed

  /**
   * GET /api/v1/complaints/{complaint_id}
   * Get single complaint details
   */
  async getComplaintDetail(complaintId: string) {
    return this.request(`/api/v1/complaints/${complaintId}`, 'GET');
  }

  /**
   * PUT /api/v1/complaints/{complaint_id}
   * Update complaint status or details
   */
  async updateComplaint(complaintId: string, updateData: any) {
    return this.request(`/api/v1/complaints/${complaintId}`, 'PUT', updateData);
  }

  /**
   * PATCH /api/v1/complaints/{complaint_id}/assign
   * Assign a complaint to a field worker
   */
  async assignComplaint(complaintId: string, payload: { assigned_to: string; status?: string }) {
    return this.request(`/api/v1/complaints/${complaintId}/assign`, 'PATCH', payload);
  }

  // ============ ANALYTICS ENDPOINTS ============
  /**
   * GET /api/v1/analytics/summary
   * Get constituency summary (requires PA or Politician role)
   */
  async getAnalyticsSummary() {
    return this.request('/api/v1/analytics/summary', 'GET');
  }

  /**
   * GET /api/v1/analytics/heatmap
   * Get ward-wise heatmap data (requires PA or Politician role)
   */
  async getHeatmapData() {
    return this.request('/api/v1/analytics/heatmap', 'GET');
  }

  // ============ COPILOT ENDPOINTS ============
  /**
   * POST /api/v1/copilot/chat
   * Send chat message to AI copilot (requires Politician role)
   */
  async sendCopilotMessage(message: string, history: any[] = [], queryType: string = 'general') {
    return this.request('/api/v1/copilot/chat', 'POST', {
      message,
      history,
      query_type: queryType,
    });
  }

  /**
   * GET /api/v1/copilot/briefing/today
   * Get today's morning briefing
   */
  async getTodayBriefing() {
    return this.request('/api/v1/copilot/briefing/today', 'GET');
  }

  // ============ HEALTH CHECK ============
  /**
   * GET /health
   * Health check endpoint
   */
  async healthCheck() {
    return this.request('/health', 'GET');
  }

  /**
   * GET /api/v1/users/workers
   * Get list of field workers
   */
  async getWorkers() {
    return this.request('/api/v1/users/workers', 'GET');
  }
}

export const apiClient = new ApiClient();
