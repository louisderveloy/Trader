/**
 * API client with JWT authentication via httpOnly cookies and error handling
 */

import axios, {type AxiosError, type AxiosInstance} from 'axios'

// Get API base URL from environment variable
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Create axios instance
export const apiClient: AxiosInstance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 15000,
    withCredentials: true,  // Send cookies with requests (httpOnly JWT token)
    headers: {
        'Content-Type': 'application/json',
    },
})

/**
 * Helper function to get a cookie value by name
 */
function getCookie(name: string): string | null {
    const value = `; ${document.cookie}`
    const parts = value.split(`; ${name}=`)
    if (parts.length === 2) {
        return parts.pop()?.split(';').shift() || null
    }
    return null
}

/**
 * Request interceptor: Add CSRF token to state-changing requests
 * JWT token is automatically sent in httpOnly cookie (no JS access for XSS protection)
 */
apiClient.interceptors.request.use(
    async (config) => {
        // For state-changing methods, include CSRF token from cookie
        if (['post', 'patch', 'put', 'delete'].includes(config.method?.toLowerCase() || '')) {
            const csrfToken = getCookie('csrf_access_token')
            if (csrfToken) {
                config.headers['X-CSRF-Token'] = csrfToken
            }
        }
        return config
    },
    (error) => Promise.reject(error)
)

/**
 * Response interceptor: Handle 401 errors (auto logout) and other errors
 */
apiClient.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
        // Handle 401 Unauthorized - redirect to login
        // httpOnly cookie will be cleared by server on logout
        if (error.response?.status === 401) {
            console.warn('Unauthorized: Redirecting to login')

            // Redirect to login page (only if not already on login page)
            if (window.location.pathname !== '/login') {
                window.location.href = '/login'
            }
        }

        // Handle 404 - Missing API endpoints
        if (error.response?.status === 404) {
            console.warn('API endpoint not available: ', error.config?.url)
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

/**
 * Fetch CSRF token from backend
 * Should be called on app initialization and after login
 */
export async function fetchCsrfToken(): Promise<void> {
    try {
        await apiClient.get('/auth/csrf-token')
    } catch (error) {
        console.error('Failed to fetch CSRF token:', error)
    }
}

export default apiClient
