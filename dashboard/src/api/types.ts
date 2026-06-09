/**
 * API type definitions for Trading Bot Dashboard
 */

// Authentication types
export interface UserLogin {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  username: string
  email: string
}

// Run types
export interface Run {
  id: number
  run_type: 'backtest' | 'optimization' | 'paper' | 'live'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  environment: 'dev' | 'staging' | 'prod'
  symbol: string
  timeframe: string
  start_date: string
  end_date: string
  config_snapshot: Record<string, any>
  result: Record<string, any> | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  weights_set_id: number | null
  optuna_study_id: number | null
}

export interface RunFilters {
  run_type?: string
  status?: string
  environment?: string
  symbol?: string
  limit?: number
  offset?: number
}

export interface RunListResponse {
  total: number
  items: Run[]
  limit: number
  offset: number
}

export interface RunStatusUpdate {
  status: string
  reason?: string
}

// Health check types
export interface HealthResponse {
  status: 'healthy' | 'degraded'
  timestamp: string
  database: string
}

// API error response
export interface ApiError {
  detail: string
}
