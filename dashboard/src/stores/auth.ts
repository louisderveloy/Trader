/**
 * Authentication store with httpOnly cookie JWT authentication
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '@/api/auth'
import type { User } from '@/api/types'
import { fetchCsrfToken } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  // State
  // Note: JWT token is stored in httpOnly cookie (not accessible to JavaScript)
  // We track authentication state via the user object
  const user = ref<User | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Auth mode mirrors the API (VITE_AUTH_MODE). In OIDC mode the dashboard never
  // shows a password form — it redirects to Authelia via the API.
  const oidcMode = import.meta.env.VITE_AUTH_MODE === 'authelia_oidc'
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  // Computed
  const isAuthenticated = computed(() => !!user.value)
  // Default to admin when the backend doesn't supply a role (local auth mode).
  const isAdmin = computed(() => (user.value?.role ?? 'admin') === 'admin')
  // Viewer or admin both grant read access; only admin sees mutating actions.
  const isViewer = computed(() => {
    const role = user.value?.role ?? 'admin'
    return role === 'viewer' || role === 'admin'
  })

  /**
   * Begin OIDC login: full-page navigation to the API (never an XHR, so the
   * browser can follow the cross-origin redirect to Authelia).
   */
  function loginRedirect(returnTo: string = '/'): void {
    const url = `${apiBaseUrl}/auth/oidc/login?return_to=${encodeURIComponent(returnTo)}`
    window.location.href = url
  }

  /**
   * Begin a step-up re-authentication (required before launching a live run).
   * Full-page navigation; on return the operator retries the action.
   */
  function redirectToStepUp(returnTo: string = '/runs'): void {
    const url = `${apiBaseUrl}/auth/oidc/stepup?return_to=${encodeURIComponent(returnTo)}`
    window.location.href = url
  }

  // Actions
  /**
   * Login with username and password
   * JWT token is automatically set in httpOnly cookie by the server
   */
  async function login(username: string, password: string): Promise<boolean> {
    isLoading.value = true
    error.value = null

    try {
      // Call login API (server sets httpOnly cookie with JWT)
      await authApi.login(username, password)

      // Fetch CSRF token for state-changing requests
      await fetchCsrfToken()

      // Fetch user info (cookie is automatically sent with request)
      await fetchUser()

      return true
    } catch (err: any) {
      console.error('Login failed:', err)
      error.value = err.response?.data?.detail || 'Échec de la connexion'
      return false
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch current user information
   */
  async function fetchUser(): Promise<void> {
    try {
      const userData = await authApi.getMe()
      user.value = userData
    } catch (err) {
      console.error('Failed to fetch user:', err)
      // Don't set error here, as it's called after successful login
    }
  }

  /**
   * Logout - call API to clear httpOnly cookie and clear user data
   */
  async function logout(): Promise<void> {
    try {
      // Call logout API (server clears httpOnly cookie). OIDC mode uses a
      // dedicated endpoint that also clears any step-up grant.
      if (oidcMode) {
        await authApi.oidcLogout()
      } else {
        await authApi.logout()
      }
    } catch (err) {
      console.error('Logout error:', err)
      // Continue with local cleanup even if API call fails
    } finally {
      // Clear local user data
      user.value = null
      error.value = null
    }
  }

  /**
   * Initialize auth state (fetch user if httpOnly cookie exists)
   * This attempts to fetch the current user on app load
   */
  async function initialize(): Promise<void> {
    if (!user.value) {
      try {
        await fetchUser()
      } catch (err) {
        // User not authenticated or session expired
        // This is normal if user hasn't logged in yet
        console.debug('No active session on initialization')
      }
    }
  }

  return {
    // State
    user,
    isLoading,
    error,
    // Config
    oidcMode,
    // Computed
    isAuthenticated,
    isAdmin,
    isViewer,
    // Actions
    login,
    loginRedirect,
    redirectToStepUp,
    logout,
    fetchUser,
    initialize,
  }
})
