/**
 * Logs API endpoints.
 *
 * API client functions for querying system logs and error logs.
 */

import { apiClient } from './client'

export interface LogEntry {
  id: string
  timestamp: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  logger: string
  message: string
  source?: string
  run_id?: string
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
 * Get list of logs with filters
 *
 * NOTE: This endpoint may not be implemented in Phase 8.
 * Using mock data for now (Wave 3).
 */
export async function getLogs(filters: LogFilters = {}): Promise<LogListResponse> {
  try {
    const params = {
      limit: filters.limit || 100,
      offset: filters.offset || 0,
      ...(filters.level && { level: filters.level }),
      ...(filters.logger && { logger: filters.logger }),
      ...(filters.search && { search: filters.search })
    }

    const response = await apiClient.get<LogListResponse>('/logs', { params })
    return response.data
  } catch (error) {
    // Fallback to mock data if endpoint doesn't exist
    return getMockLogs(filters)
  }
}

/**
 * Mock logs for development
 * Remove when API endpoint is implemented
 */
function getMockLogs(filters: LogFilters = {}): LogListResponse {
  const mockLogs: LogEntry[] = [
    {
      id: 'log-1',
      timestamp: new Date(Date.now() - 60000).toISOString(),
      level: 'INFO',
      logger: 'bot.strategy',
      message: 'Signal generated: BUY (score: 0.78)',
      source: 'BotStrategy',
      run_id: 'run-123'
    },
    {
      id: 'log-2',
      timestamp: new Date(Date.now() - 120000).toISOString(),
      level: 'INFO',
      logger: 'bot.exchange',
      message: 'Order filled: BUY 0.5 BTC @ 45000 USDT',
      source: 'BinanceExchange',
      run_id: 'run-123'
    },
    {
      id: 'log-3',
      timestamp: new Date(Date.now() - 180000).toISOString(),
      level: 'WARNING',
      logger: 'bot.exchange',
      message: 'High latency detected: 2500ms',
      source: 'BinanceExchange',
      run_id: 'run-123'
    },
    {
      id: 'log-4',
      timestamp: new Date(Date.now() - 240000).toISOString(),
      level: 'ERROR',
      logger: 'bot.risk',
      message: 'Max daily quota reached: 5 trades',
      source: 'RiskManager',
      run_id: 'run-123'
    },
    {
      id: 'log-5',
      timestamp: new Date(Date.now() - 300000).toISOString(),
      level: 'DEBUG',
      logger: 'bot.indicators',
      message: 'Calculated RSI: 65.23 (overbought)',
      source: 'Indicators',
      run_id: 'run-123'
    }
  ]

  // Apply filters
  let filtered = mockLogs

  if (filters.level) {
    filtered = filtered.filter(log => log.level === filters.level)
  }

  if (filters.logger) {
    filtered = filtered.filter(log => log.logger.includes(filters.logger!))
  }

  if (filters.search) {
    const searchLower = filters.search.toLowerCase()
    filtered = filtered.filter(log => log.message.toLowerCase().includes(searchLower))
  }

  // Pagination
  const offset = filters.offset || 0
  const limit = filters.limit || 100
  const items = filtered.slice(offset, offset + limit)

  return {
    total: filtered.length,
    items,
    limit,
    offset
  }
}
