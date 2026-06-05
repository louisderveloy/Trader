import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { LogEntry, LogFilters, getLogs } from '@/api/logs'

export const useLogsStore = defineStore('logs', () => {
  // State
  const logs = ref<LogEntry[]>([])
  const total = ref(0)
  const isLoading = ref(false)
  const isAutoRefreshing = ref(false)
  const error = ref<string | null>(null)

  // Pagination
  const limit = ref(50)
  const offset = ref(0)

  // Filters
  const filters = ref<LogFilters>({
    level: undefined,
    logger: undefined,
    search: undefined,
    limit: 50,
    offset: 0
  })

  // Auto-refresh interval
  let autoRefreshInterval: ReturnType<typeof setInterval> | null = null

  // Computed
  const hasMore = computed(() => offset.value + limit.value < total.value)
  const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1)
  const totalPages = computed(() => Math.ceil(total.value / limit.value))

  const logSummary = computed(() => {
    const summary = {
      debug: 0,
      info: 0,
      warning: 0,
      error: 0,
      critical: 0
    }

    logs.value.forEach(log => {
      const key = log.level.toLowerCase() as keyof typeof summary
      summary[key]++
    })

    return summary
  })

  // Actions
  async function fetchLogs(newFilters?: LogFilters): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      if (newFilters) {
        filters.value = {
          ...filters.value,
          ...newFilters,
          limit: limit.value,
          offset: offset.value
        }
      }

      const response = await getLogs({
        ...filters.value,
        limit: limit.value,
        offset: offset.value
      })

      logs.value = response.items
      total.value = response.total
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch logs'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function setFilters(newFilters: Partial<LogFilters>): void {
    filters.value = { ...filters.value, ...newFilters }
    offset.value = 0 // Reset pagination
  }

  function setLevelFilter(level: string | undefined): void {
    filters.value.level = level
    offset.value = 0
  }

  function setSearchFilter(search: string | undefined): void {
    filters.value.search = search
    offset.value = 0
  }

  function clearFilters(): void {
    filters.value = {
      level: undefined,
      logger: undefined,
      search: undefined,
      limit: limit.value,
      offset: 0
    }
    offset.value = 0
  }

  function startAutoRefresh(intervalMs: number = 5000): void {
    isAutoRefreshing.value = true

    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval)
    }

    autoRefreshInterval = setInterval(() => {
      fetchLogs()
    }, intervalMs)
  }

  function stopAutoRefresh(): void {
    isAutoRefreshing.value = false
    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval)
      autoRefreshInterval = null
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
    logs,
    total,
    isLoading,
    isAutoRefreshing,
    error,
    filters,
    limit,
    offset,

    // Computed
    hasMore,
    currentPage,
    totalPages,
    logSummary,

    // Actions
    fetchLogs,
    setFilters,
    setLevelFilter,
    setSearchFilter,
    clearFilters,
    startAutoRefresh,
    stopAutoRefresh,
    nextPage,
    previousPage,
    resetPagination
  }
})
