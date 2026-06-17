/**
 * Authentication API calls
 */

import apiClient from './client'
import type { UserLogin, User } from './types'

interface LoginResponse {
  message: string
  username: string
}

/**
 * Login with username and password
 * JWT token is automatically set in httpOnly cookie by the server
 */
export async function login(username: string, password: string): Promise<LoginResponse> {
  const credentials: UserLogin = { username, password }
  const response = await apiClient.post<LoginResponse>('/auth/login', credentials)
  return response.data
}

/**
 * Logout - clears httpOnly cookie on server (local mode)
 */
export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout')
}

/**
 * Logout in OIDC mode - clears the session and any step-up grant.
 */
export async function oidcLogout(): Promise<void> {
  await apiClient.post('/auth/oidc/logout')
}

/**
 * Get current user information
 */
export async function getMe(): Promise<User> {
  const response = await apiClient.get<User>('/auth/me')
  return response.data
}
