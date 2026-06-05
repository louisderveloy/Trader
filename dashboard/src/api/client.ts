/**
 * API client with JWT authentication and error handling
 */

import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'

// Get API base URL from environment variable
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Create axios instance
export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Request interceptor: Add JWT token to all requests
 */
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Get token from localStorage
    const token = localStorage.getItem('auth_token')

    if (token) {
      // Remove quotes if present (localStorage stores strings with quotes sometimes)
      const cleanToken = token.replace(/^"(.*)"$/, '$1')
      config.headers.Authorization = `Bearer ${cleanToken}`
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * Response interceptor: Handle 401 errors (auto logout) and other errors
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Handle 401 Unauthorized - auto logout and redirect to login
    if (error.response?.status === 401) {
      console.warn('Unauthorized: Auto-logout triggered')

      // Clear token from localStorage
      localStorage.removeItem('auth_token')

      // Redirect to login page (only if not already on login page)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }

    // Handle 404 - Missing API endpoints (Phase 8 TODOs)
    if (error.response?.status === 404) {
      console.warn('API endpoint not yet implemented:', error.config?.url)
    }

    // Log other errors
    if (error.response) {
      // Server responded with error status
      console.error('API error:', {
        status: error.response.status,
        url: error.config?.url,
        data: error.response.data,
      })
    } else if (error.request) {
      // Request made but no response received
      console.error('Network error: No response from server', error.request)
    } else {
      // Something else happened
      console.error('Request error:', error.message)
    }

    return Promise.reject(error)
  }
)

export default apiClient
