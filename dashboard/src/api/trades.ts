/**
 * Trades API endpoints.
 *
 * API client functions for querying and analyzing completed trades.
 */

import { apiClient } from './client'

export interface Trade {
  id: string
  run_id: string
  symbol: string
  side: 'long' | 'short'
  environment: 'testnet' | 'live' | 'paper' | 'backtest'
  status: 'open' | 'closed'
  entry_price: number
  exit_price: number | null
  quantity: number
  pnl: number | null
  pnl_percent: number | null
  commission_total: number
  opened_at: string
  closed_at: string | null
  duration_seconds: number | null
  created_at: string
}

export interface TradeListResponse {
  total: number
  items: Trade[]
  limit: number
  offset: number
}

export interface TradeFilters {
  run_id?: string
  symbol?: string
  side?: 'long' | 'short'
  environment?: 'testnet' | 'live' | 'paper' | 'backtest'
  min_pnl?: number
  max_pnl?: number
  /** ISO 8601 lower bound on trade open time (inclusive). */
  start_date?: string
  /** ISO 8601 upper bound on trade open time (inclusive). */
  end_date?: string
  sort_by?: 'result' | 'duration'
  sort_dir?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

/**
 * Get list of trades with filters
 */
export async function getTrades(filters: TradeFilters = {}): Promise<TradeListResponse> {
  const params = {
    limit: filters.limit || 100,
    offset: filters.offset || 0,
    ...(filters.run_id && { run_id: filters.run_id }),
    ...(filters.symbol && { symbol: filters.symbol }),
    ...(filters.side && { side: filters.side }),
    ...(filters.environment && { environment: filters.environment }),
    ...(filters.min_pnl !== undefined && { min_pnl: filters.min_pnl }),
    ...(filters.max_pnl !== undefined && { max_pnl: filters.max_pnl }),
    ...(filters.start_date && { start_date: filters.start_date }),
    ...(filters.end_date && { end_date: filters.end_date }),
    ...(filters.sort_by && filters.sort_dir && { sort_by: filters.sort_by, sort_dir: filters.sort_dir })
  }

  const response = await apiClient.get<TradeListResponse>('/trades', { params })
  return response.data
}

/**
 * Get trade by ID
 */
export async function getTrade(tradeId: string): Promise<Trade> {
  const response = await apiClient.get<Trade>(`/trades/${tradeId}`)
  return response.data
}
