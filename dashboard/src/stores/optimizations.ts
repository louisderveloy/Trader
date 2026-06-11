import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import {
  Optimization,
  LaunchOptimizationRequest,
  getOptimizations,
  getOptimization,
  launchOptimization,
  activateOptimizationWeights,
} from '@/api/optimizations'
import { stopRun, killRun, getRunLogs } from '@/api/runs'
import type { RunLogsResponse } from '@/api/types'
import { useToastStore } from '@/stores/toast'

export const useOptimizationsStore = defineStore('optimizations', () => {
  // State
  const optimizations = ref<Optimization[]>([])
  const selectedOptimization = ref<Optimization | null>(null)
  const total = ref(0)
  const isLoading = ref(false)
  const isLaunching = ref(false)
  const error = ref<string | null>(null)
  // run_id whose weights set is currently being activated (for button state)
  const activatingWeightsRunId = ref<number | null>(null)

  // Pagination
  const limit = ref(20)
  const offset = ref(0)

  // Polling instance
  let pollingInstance: ReturnType<typeof useIntervalFn> | null = null

  // Computed
  const hasMore = computed(() => offset.value + limit.value < total.value)
  const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1)
  const totalPages = computed(() => Math.ceil(total.value / limit.value))
  const hasActive = computed(() =>
    optimizations.value.some((o) => o.status === 'pending' || o.status === 'running')
  )

  // Actions
  async function fetchOptimizations(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const response = await getOptimizations(limit.value, offset.value)
      optimizations.value = response.items
      total.value = response.total
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch optimizations'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchOptimization(runId: number): Promise<void> {
    error.value = null
    try {
      selectedOptimization.value = await getOptimization(runId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch optimization'
      throw err
    }
  }

  async function launch(request: LaunchOptimizationRequest): Promise<number | null> {
    const toast = useToastStore()
    isLaunching.value = true
    error.value = null
    try {
      const res = await launchOptimization(request)
      toast.success(`Optimisation #${res.run_id} démarrée`)
      await fetchOptimizations()
      return res.run_id
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Erreur lors du lancement de l\'optimisation'
      error.value = typeof detail === 'string' ? detail : 'Paramètres invalides'
      toast.error(error.value)
      return null
    } finally {
      isLaunching.value = false
    }
  }

  async function stopOptimization(runId: number): Promise<boolean> {
    const toast = useToastStore()
    try {
      await stopRun(runId)
      toast.success(`Arrêt de l'optimisation #${runId} demandé`)
      await fetchOptimizations()
      return true
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Erreur lors de l'arrêt de l'optimisation")
      return false
    }
  }

  async function killOptimization(runId: number): Promise<boolean> {
    const toast = useToastStore()
    try {
      await killRun(runId)
      toast.success(`Optimisation #${runId} tuée`)
      await fetchOptimizations()
      return true
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Erreur lors du kill de l'optimisation")
      return false
    }
  }

  async function activateWeights(runId: number): Promise<boolean> {
    const toast = useToastStore()
    activatingWeightsRunId.value = runId
    try {
      await activateOptimizationWeights(runId)
      toast.success(`Jeu de poids de l'optimisation #${runId} activé`)
      // Refresh so every card reflects the new exclusive active set.
      await fetchOptimizations()
      return true
    } catch (err: any) {
      toast.error(
        err.response?.data?.detail || "Erreur lors de l'activation du jeu de poids"
      )
      return false
    } finally {
      activatingWeightsRunId.value = null
    }
  }

  async function fetchLogs(runId: number): Promise<RunLogsResponse | null> {
    try {
      return await getRunLogs(runId)
    } catch (err) {
      console.error('Failed to fetch optimization logs:', err)
      return null
    }
  }

  function nextPage(): void {
    if (hasMore.value) {
      offset.value += limit.value
    }
  }

  function previousPage(): void {
    if (offset.value > 0) {
      offset.value = Math.max(0, offset.value - limit.value)
    }
  }

  function resetPagination(): void {
    offset.value = 0
  }

  function startPolling(intervalMs: number = 10000): void {
    if (pollingInstance) {
      pollingInstance.pause()
    }
    pollingInstance = useIntervalFn(() => {
      // Only refresh automatically while something is in flight.
      if (hasActive.value) {
        fetchOptimizations()
      }
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollingInstance) {
      pollingInstance.pause()
      pollingInstance = null
    }
  }

  return {
    // State
    optimizations,
    selectedOptimization,
    total,
    isLoading,
    isLaunching,
    error,
    activatingWeightsRunId,
    limit,
    offset,

    // Computed
    hasMore,
    currentPage,
    totalPages,
    hasActive,

    // Actions
    fetchOptimizations,
    fetchOptimization,
    launch,
    stopOptimization,
    killOptimization,
    activateWeights,
    fetchLogs,
    nextPage,
    previousPage,
    resetPagination,
    startPolling,
    stopPolling,
  }
})
