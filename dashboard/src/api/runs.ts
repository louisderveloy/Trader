/**
 * Runs API calls
 */

import apiClient from './client'
import type {
  Run,
  RunCommandResponse,
  RunFilters,
  RunListResponse,
  RunLogsResponse,
  RunStatusUpdate,
  StartRunRequest,
  StartRunResponse,
  SymbolsResponse,
} from './types'

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

/**
 * Start a run (backtest, paper or live)
 */
export async function startRun(payload: StartRunRequest): Promise<StartRunResponse> {
  const response = await apiClient.post<StartRunResponse>('/runs/start', payload)
  return response.data
}

/**
 * Request a graceful stop (SIGTERM) of a run
 */
export async function stopRun(runId: number): Promise<RunCommandResponse> {
  const response = await apiClient.post<RunCommandResponse>(`/runs/${runId}/stop`)
  return response.data
}

/**
 * Force-kill a run (backtest only)
 */
export async function killRun(runId: number): Promise<RunCommandResponse> {
  const response = await apiClient.post<RunCommandResponse>(`/runs/${runId}/kill`)
  return response.data
}

/**
 * Get the last log lines for a run (snapshot)
 */
export async function getRunLogs(runId: number): Promise<RunLogsResponse> {
  const response = await apiClient.get<RunLogsResponse>(`/runs/${runId}/logs`)
  return response.data
}

/**
 * List the trading symbols selectable when starting a run
 */
export async function getSymbols(): Promise<SymbolsResponse> {
  const response = await apiClient.get<SymbolsResponse>('/runs/symbols')
  return response.data
}
