import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  Optimization,
  OptimizationListResponse,
  LaunchOptimizationRequest,
  getOptimizations,
  getOptimization,
  launchOptimization
} from '@/api/optimizations'

export const useOptimizationsStore = defineStore('optimizations', () => {
  // State
  const optimizations = ref<Optimization[]>([])
  const selectedOptimization = ref<Optimization | null>(null)
  const total = ref(0)
  const isLoading = ref(false)
  const isLaunching = ref(false)
  const error = ref<string | null>(null)

  // Pagination
  const limit = ref(20)
  const offset = ref(0)

  // Computed
  const hasMore = computed(() => offset.value + limit.value < total.value)
  const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1)
  const totalPages = computed(() => Math.ceil(total.value / limit.value))

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

  async function fetchOptimization(studyId: number): Promise<void> {
    error.value = null
    try {
      selectedOptimization.value = await getOptimization(studyId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch optimization'
      throw err
    }
  }

  async function launch(request: LaunchOptimizationRequest): Promise<void> {
    isLaunching.value = true
    error.value = null
    try {
      const newStudy = await launchOptimization(request)
      optimizations.value.unshift(newStudy)
      total.value += 1
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to launch optimization'
      throw err
    } finally {
      isLaunching.value = false
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

  return {
    // State
    optimizations,
    selectedOptimization,
    total,
    isLoading,
    isLaunching,
    error,
    limit,
    offset,

    // Computed
    hasMore,
    currentPage,
    totalPages,

    // Actions
    fetchOptimizations,
    fetchOptimization,
    launch,
    nextPage,
    previousPage,
    resetPagination
  }
})
