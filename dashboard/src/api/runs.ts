/**
 * Runs API calls
 */

import apiClient from './client'
import type { Run, RunFilters, RunListResponse, RunStatusUpdate } from './types'

/**
 * List runs with filtering and pagination
 */
export async function listRuns(filters: RunFilters = {}): Promise<RunListResponse> {
  const params = {
    ...(filters.run_type && { run_type: filters.run_type }),
    ...(filters.status && { status: filters.status }),
    ...(filters.environment && { environment: filters.environment }),
    ...(filters.symbol && { symbol: filters.symbol }),
    limit: filters.limit || 20,
    offset: filters.offset || 0,
  }

  const response = await apiClient.get<RunListResponse>('/runs', { params })
  return response.data
}

/**
 * Get active runs (pending or running)
 */
export async function getActiveRuns(): Promise<Run[]> {
  const response = await apiClient.get<Run[]>('/runs/active')
  return response.data
}

/**
 * Get single run by ID
 */
export async function getRun(runId: number): Promise<Run> {
  const response = await apiClient.get<Run>(`/runs/${runId}`)
  return response.data
}

/**
 * Update run status
 */
export async function updateRunStatus(
  runId: number,
  update: RunStatusUpdate
): Promise<Run> {
  const response = await apiClient.patch<Run>(`/runs/${runId}/status`, update)
  return response.data
}
