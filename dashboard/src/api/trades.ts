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
  direction: 'long' | 'short'
  entry_price: number
  entry_time: string
  entry_size: number
  exit_price: number | null
  exit_time: string | null
  pnl: number | null
  pnl_percent: number | null
  fees: number
  slippage: number | null
  stop_loss_price: number | null
  take_profit_price: number | null
  exit_reason: string | null
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
  direction?: 'long' | 'short'
  min_pnl?: number
  max_pnl?: number
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
    ...(filters.direction && { direction: filters.direction }),
    ...(filters.min_pnl !== undefined && { min_pnl: filters.min_pnl }),
    ...(filters.max_pnl !== undefined && { max_pnl: filters.max_pnl })
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
