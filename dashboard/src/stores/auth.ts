/**
 * Authentication store with JWT token management
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useStorage } from '@vueuse/core'
import * as authApi from '@/api/auth'
import type { User } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  // State
  // Token persisted in localStorage via useStorage
  const token = useStorage<string | null>('auth_token', null)
  const user = ref<User | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const isAuthenticated = computed(() => !!token.value)

  // Actions
  /**
   * Login with username and password
   */
  async function login(username: string, password: string): Promise<boolean> {
    isLoading.value = true
    error.value = null

    try {
      // Call login API
      const response = await authApi.login(username, password)

      // Save token to localStorage (useStorage handles persistence)
      token.value = response.access_token

      // Fetch user info
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
   * Logout - clear token and user data
   */
  function logout(): void {
    token.value = null
    user.value = null
    error.value = null
  }

  /**
   * Initialize auth state (fetch user if token exists)
   */
  async function initialize(): Promise<void> {
    if (token.value && !user.value) {
      await fetchUser()
    }
  }

  return {
    // State
    token,
    user,
    isLoading,
    error,
    // Computed
    isAuthenticated,
    // Actions
    login,
    logout,
    fetchUser,
    initialize,
  }
})
