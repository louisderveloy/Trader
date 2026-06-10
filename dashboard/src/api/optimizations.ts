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

/**
 * Get list of optimization runs (newest first)
 */
export async function getOptimizations(
  limit: number = 100,
  offset: number = 0
): Promise<OptimizationListResponse> {
  const response = await apiClient.get<OptimizationListResponse>('/optimizations', {
    params: { limit, offset },
  })
  return response.data
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
