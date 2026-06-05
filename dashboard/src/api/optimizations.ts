/**
 * Optimizations API endpoints.
 *
 * API client functions for managing Optuna optimization studies.
 */

import { apiClient } from './client'

export interface OptimizationTrial {
  trial_number: number
  value: number
  state: 'complete' | 'pruned' | 'fail'
  params: Record<string, unknown>
  metrics: Record<string, unknown>
}

export interface Optimization {
  id: number
  run_id: string
  name: string
  direction: 'maximize' | 'minimize'
  objective: 'sharpe' | 'sortino' | 'profit_factor'
  n_trials: number
  n_jobs: number
  sampler: string
  pruner: string
  best_value: number | null
  best_params: Record<string, unknown> | null
  best_trial: OptimizationTrial | null
  walk_forward_splits: number
  walk_forward_train_ratio: number
  status: 'running' | 'completed' | 'failed' | 'stopped'
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface OptimizationListResponse {
  total: number
  items: Optimization[]
  limit: number
  offset: number
}

export interface LaunchOptimizationRequest {
  name: string
  objective: 'sharpe' | 'sortino' | 'profit_factor'
  n_trials: number
  n_jobs: number
}

/**
 * Get list of optimization studies
 */
export async function getOptimizations(limit: number = 100, offset: number = 0): Promise<OptimizationListResponse> {
  const response = await apiClient.get<OptimizationListResponse>('/optimizations', {
    params: { limit, offset }
  })
  return response.data
}

/**
 * Get optimization study by ID
 */
export async function getOptimization(studyId: number): Promise<Optimization> {
  const response = await apiClient.get<Optimization>(`/optimizations/${studyId}`)
  return response.data
}

/**
 * Launch new optimization study
 */
export async function launchOptimization(request: LaunchOptimizationRequest): Promise<Optimization> {
  const response = await apiClient.post<Optimization>('/optimizations', request)
  return response.data
}
