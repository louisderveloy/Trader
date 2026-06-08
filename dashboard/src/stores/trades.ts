import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { Trade, TradeFilters, getTrades, getTrade } from '@/api/trades'

export const useTradesStore = defineStore('trades', () => {
  // State
  const trades = ref<Trade[]>([])
  const selectedTrade = ref<Trade | null>(null)
  const total = ref(0)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Pagination
  const limit = ref(50)
  const offset = ref(0)

  // Filters
  const filters = ref<TradeFilters>({
    limit: 50,
    offset: 0
  })

  // Computed
  const hasMore = computed(() => offset.value + limit.value < total.value)
  const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1)
  const totalPages = computed(() => Math.ceil(total.value / limit.value))

  // Statistics
  const stats = computed(() => {
    if (trades.value.length === 0) {
      return {
        totalTrades: 0,
        openTrades: 0,
        closedTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        winRate: 0,
        totalPnl: 0,
        avgPnl: 0,
        bestTrade: 0,
        worstTrade: 0
      }
    }

    // Separate open and closed trades
    const openTrades = trades.value.filter(t => t.status === 'open')
    const closedTrades = trades.value.filter(t => t.status === 'closed')

    if (closedTrades.length === 0) {
      return {
        totalTrades: trades.value.length,
        openTrades: openTrades.length,
        closedTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        winRate: 0,
        totalPnl: 0,
        avgPnl: 0,
        bestTrade: 0,
        worstTrade: 0
      }
    }

    // Calculate stats only for closed trades (open trades have no pnl yet)
    const pnlValues = closedTrades.map(t => {
      if (!t.pnl) return 0
      if (typeof t.pnl === 'number') return t.pnl
      if (typeof t.pnl === 'string') return parseFloat(t.pnl)
      return 0
    })

    const winningTrades = pnlValues.filter(pnl => pnl > 0).length
    const losingTrades = pnlValues.filter(pnl => pnl < 0).length
    const totalPnl = pnlValues.reduce((sum, pnl) => sum + pnl, 0)
    const avgPnl = totalPnl / pnlValues.length
    const bestTrade = Math.max(...pnlValues, 0)
    const worstTrade = Math.min(...pnlValues, 0)

    return {
      totalTrades: trades.value.length,
      openTrades: openTrades.length,
      closedTrades: closedTrades.length,
      winningTrades,
      losingTrades,
      winRate: closedTrades.length > 0 ? (winningTrades / closedTrades.length) * 100 : 0,
      totalPnl,
      avgPnl,
      bestTrade,
      worstTrade
    }
  })

  // Actions
  async function fetchTrades(newFilters?: TradeFilters): Promise<void> {
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

      const response = await getTrades({
        ...filters.value,
        limit: limit.value,
        offset: offset.value
      })

      trades.value = response.items
      total.value = response.total
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch trades'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTrade(tradeId: string): Promise<void> {
    error.value = null
    try {
      selectedTrade.value = await getTrade(tradeId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch trade'
      throw err
    }
  }

  function setFilters(newFilters: Partial<TradeFilters>): void {
    filters.value = { ...filters.value, ...newFilters }
    offset.value = 0 // Reset pagination
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
    trades,
    selectedTrade,
    total,
    isLoading,
    error,
    filters,
    limit,
    offset,

    // Computed
    hasMore,
    currentPage,
    totalPages,
    stats,

    // Actions
    fetchTrades,
    fetchTrade,
    setFilters,
    nextPage,
    previousPage,
    resetPagination
  }
})
