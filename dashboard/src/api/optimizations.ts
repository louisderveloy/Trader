/**
 * Optimizations API endpoints.
 *
 * An optimization is a run (run_type='optimization'). Launch goes through the
 * /optimizations namespace; stop/kill/logs reuse the generic /runs/{id}/...
 * endpoints (keyed by run_id).
 */

import { apiClient } from './client'

export type OptimizationStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface Optimization {
  run_id: number
  status: OptimizationStatus
  symbol: string | null
  timeframe: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  study_name: string
  objective: string | null
  n_trials: number | null
  n_splits: number | null
  study_id: string | null
  best_value: number | null
  best_params: Record<string, unknown> | null
  weights_set_id: string | null
  weights_set_active: boolean
}

export interface OptimizationListResponse {
  total: number
  items: Optimization[]
  limit: number
  offset: number
}

export type OptimizationObjective =
  | 'sharpe_ratio'
  | 'sortino_ratio'
  | 'profit_factor'
  | 'win_rate'
  | 'total_return'

export interface LaunchOptimizationRequest {
  study_name: string
  symbol: string
  timeframe: string
  objective: OptimizationObjective
  n_trials: number
  n_splits: number
  // Optional / advanced
  start_date?: string
  end_date?: string
  train_ratio?: number
  walk_forward_mode?: 'sliding' | 'expanding'
  sampler?: 'tpe' | 'random' | 'grid' | 'cmaes'
  pruner?: 'median' | 'hyperband' | 'none'
  multithread?: boolean
}

export interface LaunchOptimizationResponse {
  run_id: number
  command_id: number
  status: string
  message: string
}

export type OptimizationSortField = 'completed_at' | 'best_value'
export type SortDirection = 'asc' | 'desc'

export interface OptimizationQuery {
  limit?: number
  offset?: number
  symbol?: string
  objective?: string
  status?: OptimizationStatus
  active_only?: boolean
  sort_by?: OptimizationSortField
  sort_dir?: SortDirection
}

/**
 * Get list of optimization runs with server-side filtering/sorting/pagination.
 * Only defined keys are sent; the backend validates every filter/sort value.
 */
export async function getOptimizations(
  query: OptimizationQuery = {}
): Promise<OptimizationListResponse> {
  const response = await apiClient.get<OptimizationListResponse>('/optimizations', {
    params: query,
  })
  return response.data
}

/**
 * Distinct symbols present in optimization runs (for the filter dropdown).
 */
export async function getOptimizationSymbols(): Promise<string[]> {
  const response = await apiClient.get<{ symbols: string[] }>('/optimizations/symbols')
  return response.data.symbols
}

/**
 * Get a single optimization run by its run id
 */
export async function getOptimization(runId: number): Promise<Optimization> {
  const response = await apiClient.get<Optimization>(`/optimizations/${runId}`)
  return response.data
}

/**
 * Launch a new optimization run
 */
export async function launchOptimization(
  request: LaunchOptimizationRequest
): Promise<LaunchOptimizationResponse> {
  const response = await apiClient.post<LaunchOptimizationResponse>('/optimizations', request)
  return response.data
}

/**
 * Activate the weights set produced by this optimization run (admin only).
 * Returns the refreshed optimization (weights_set_active will be true).
 */
export async function activateOptimizationWeights(runId: number): Promise<Optimization> {
  const response = await apiClient.post<Optimization>(`/optimizations/${runId}/activate-weights`)
  return response.data
}
