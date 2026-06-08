/**
 * Logs API endpoints.
 *
 * API client functions for querying system logs and error logs.
 */

import { apiClient } from './client'

// API response from errors_log table
interface ErrorLogResponse {
  id: string
  run_id?: number
  category: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  error_message: string
  error_traceback?: string
  timestamp: string
  context?: Record<string, unknown>
}

interface ErrorLogListResponse {
  total: number
  items: ErrorLogResponse[]
  limit: number
  offset: number
}

// UI-friendly log entry
export interface LogEntry {
  id: string
  timestamp: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  logger: string
  message: string
  source?: string
  run_id?: number
}

export interface LogListResponse {
  total: number
  items: LogEntry[]
  limit: number
  offset: number
}

export interface LogFilters {
  level?: string
  logger?: string
  search?: string
  limit?: number
  offset?: number
}

/**
 * Map severity to log level
 */
function severityToLevel(severity: string): LogEntry['level'] {
  const mapping: Record<string, LogEntry['level']> = {
    'low': 'INFO',
    'medium': 'WARNING',
    'high': 'ERROR',
    'critical': 'CRITICAL'
  }
  return mapping[severity] || 'ERROR'
}

/**
 * Map log level to severity for API filtering
 */
function levelToSeverity(level: string): string {
  const mapping: Record<string, string> = {
    'DEBUG': 'low',
    'INFO': 'low',
    'WARNING': 'medium',
    'ERROR': 'high',
    'CRITICAL': 'critical'
  }
  return mapping[level] || level.toLowerCase()
}

/**
 * Map API error log to UI log entry
 */
function mapErrorLogToLogEntry(error: ErrorLogResponse): LogEntry {
  return {
    id: error.id,
    timestamp: error.timestamp,
    level: severityToLevel(error.severity),
    logger: error.category,
    message: error.error_message,
    source: error.context?.source as string | undefined,
    run_id: error.run_id ?? undefined
  }
}

/**
 * Get list of logs with filters
 */
export async function getLogs(filters: LogFilters = {}): Promise<LogListResponse> {
  const params: Record<string, unknown> = {
    limit: filters.limit || 100,
    offset: filters.offset || 0
  }

  // Map UI filters to API filters
  if (filters.level) {
    params.severity = levelToSeverity(filters.level)
  }

  if (filters.logger) {
    params.category = filters.logger
  }

  // Note: API doesn't support generic search yet, would need backend enhancement
  // For now, we'll filter client-side if needed

  const response = await apiClient.get<ErrorLogListResponse>('/logs', { params })

  // Map API response to UI format
  let items = response.data.items.map(mapErrorLogToLogEntry)

  // Client-side search filter if provided (temporary until API supports it)
  if (filters.search) {
    const searchLower = filters.search.toLowerCase()
    items = items.filter(log => log.message.toLowerCase().includes(searchLower))
  }

  return {
    total: response.data.total,
    items,
    limit: response.data.limit,
    offset: response.data.offset
  }
}
