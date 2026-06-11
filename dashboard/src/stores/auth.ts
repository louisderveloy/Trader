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

  // Computed
  const isAuthenticated = computed(() => !!user.value)
  // Default to admin when the backend doesn't supply a role (local auth mode).
  const isAdmin = computed(() => (user.value?.role ?? 'admin') === 'admin')

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
      // Call logout API (server clears httpOnly cookie)
      await authApi.logout()
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
    // Computed
    isAuthenticated,
    isAdmin,
    // Actions
    login,
    logout,
    fetchUser,
    initialize,
  }
})
