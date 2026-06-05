/**
 * Runs store with polling for real-time updates
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import * as runsApi from '@/api/runs'
import type { Run, RunFilters } from '@/api/types'

export const useRunsStore = defineStore('runs', () => {
  // State
  const runs = ref<Run[]>([])
  const activeRuns = ref<Run[]>([])
  const total = ref(0)
  const limit = ref(20)
  const offset = ref(0)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Polling instance
  let pollingInstance: ReturnType<typeof useIntervalFn> | null = null

  // Actions
  /**
   * Fetch runs with filters
   */
  async function fetchRuns(filters: RunFilters = {}): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const params: RunFilters = {
        ...filters,
        limit: filters.limit || limit.value,
        offset: filters.offset || offset.value,
      }

      const response = await runsApi.listRuns(params)

      runs.value = response.items
      total.value = response.total
      limit.value = response.limit
      offset.value = response.offset
    } catch (err: any) {
      console.error('Failed to fetch runs:', err)
      error.value = err.response?.data?.detail || 'Erreur lors du chargement des runs'
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch active runs (pending/running)
   */
  async function fetchActiveRuns(): Promise<void> {
    try {
      const response = await runsApi.getActiveRuns()
      activeRuns.value = response
    } catch (err) {
      console.error('Failed to fetch active runs:', err)
      // Don't set error for active runs polling - it's background operation
    }
  }

  /**
   * Get single run by ID
   */
  async function getRun(runId: number): Promise<Run | null> {
    try {
      return await runsApi.getRun(runId)
    } catch (err) {
      console.error('Failed to fetch run:', err)
      return null
    }
  }

  /**
   * Update run status
   */
  async function updateStatus(runId: number, status: string, reason?: string): Promise<boolean> {
    try {
      await runsApi.updateRunStatus(runId, { status, reason })
      // Refresh runs list
      await fetchRuns()
      return true
    } catch (err: any) {
      console.error('Failed to update run status:', err)
      error.value = err.response?.data?.detail || 'Erreur lors de la mise à jour du status'
      return false
    }
  }

  /**
   * Go to next page
   */
  function nextPage(): void {
    offset.value += limit.value
    fetchRuns()
  }

  /**
   * Go to previous page
   */
  function previousPage(): void {
    offset.value = Math.max(0, offset.value - limit.value)
    fetchRuns()
  }

  /**
   * Start polling for active runs
   */
  function startPolling(intervalMs: number = 10000): void {
    if (pollingInstance) {
      pollingInstance.pause()
    }

    // Initial fetch
    fetchActiveRuns()

    // Start polling
    pollingInstance = useIntervalFn(() => {
      fetchActiveRuns()
    }, intervalMs)
  }

  /**
   * Stop polling
   */
  function stopPolling(): void {
    if (pollingInstance) {
      pollingInstance.pause()
      pollingInstance = null
    }
  }

  return {
    // State
    runs,
    activeRuns,
    total,
    limit,
    offset,
    isLoading,
    error,
    // Actions
    fetchRuns,
    fetchActiveRuns,
    getRun,
    updateStatus,
    nextPage,
    previousPage,
    startPolling,
    stopPolling,
  }
})
