/**
 * Authentication API calls
 */

import apiClient from './client'
import type { UserLogin, TokenResponse, User } from './types'

/**
 * Login with username and password
 */
export async function login(username: string, password: string): Promise<TokenResponse> {
  const credentials: UserLogin = { username, password }
  const response = await apiClient.post<TokenResponse>('/auth/login', credentials)
  return response.data
}

/**
 * Get current user information
 */
export async function getMe(): Promise<User> {
  const response = await apiClient.get<User>('/auth/me')
  return response.data
}
