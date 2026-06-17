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
  display_name?: string | null
  email: string | null
  role?: 'admin' | 'viewer'
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
  weights_set_id: string | null
  optuna_study_id: string | null
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

// Run control (start/stop/kill + logs)
export type StartRunType = 'backtest' | 'paper' | 'live'

export interface StartRunRequest {
  run_type: StartRunType
  symbol?: string
  timeframe?: string
  // backtest
  start_date?: string
  end_date?: string
  initial_capital?: number
  weights_set_id?: string
  engine?: 'vectorbt' | 'event_driven'
  save?: boolean
  // live
  testnet?: boolean
  confirm_phrase?: string
}

export interface StartRunResponse {
  run_id: number
  command_id: number
  status: string
  message: string
}

export interface RunCommandResponse {
  run_id: number
  command_id: number
  kind: string
  message: string
}

export interface RunLogsResponse {
  run_id: number
  lines: string[]
  truncated: boolean
}

export interface SymbolsResponse {
  symbols: string[]
  default: string
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
