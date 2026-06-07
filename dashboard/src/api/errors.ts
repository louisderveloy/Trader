/**
 * Errors API endpoints.
 *
 * API client functions for querying error logs from errors_log table.
 */

import { apiClient } from './client'

export interface ErrorLog {
  id: string
  run_id: string | null
  category: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  error_message: string
  error_traceback: string | null
  timestamp: string
  context: Record<string, unknown> | null
}

export interface ErrorLogListResponse {
  total: number
  items: ErrorLog[]
  limit: number
  offset: number
}

export interface ErrorStats {
  total_errors: number
  by_severity: Record<string, number>
  by_category: Record<string, number>
  recent_24h: number
}

export interface ErrorFilters {
  severity?: string
  category?: string
  start_date?: string
  end_date?: string
  run_id?: string
  limit?: number
  offset?: number
}

/**
 * Get list of error logs with filters
 */
export async function listErrors(filters: ErrorFilters = {}): Promise<ErrorLogListResponse> {
  const params = {
    limit: filters.limit || 50,
    offset: filters.offset || 0,
    ...(filters.severity && { severity: filters.severity }),
    ...(filters.category && { category: filters.category }),
    ...(filters.start_date && { start_date: filters.start_date }),
    ...(filters.end_date && { end_date: filters.end_date }),
    ...(filters.run_id && { run_id: filters.run_id }),
  }

  const response = await apiClient.get<ErrorLogListResponse>('/errors', { params })
  return response.data
}

/**
 * Get error statistics
 */
export async function getErrorStats(): Promise<ErrorStats> {
  const response = await apiClient.get<ErrorStats>('/errors/stats')
  return response.data
}

/**
 * Get available error categories
 */
export async function getErrorCategories(): Promise<string[]> {
  const response = await apiClient.get<string[]>('/errors/categories')
  return response.data
}

/**
 * Get single error by ID
 */
export async function getError(id: string): Promise<ErrorLog> {
  const response = await apiClient.get<ErrorLog>(`/errors/${id}`)
  return response.data
}
