<template>
  <AppLayout>
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <h1 class="text-3xl font-bold text-gray-900">Tableau de bord</h1>
      </div>

      <!-- Selectors: Period & Network -->
      <div class="bg-white rounded-lg shadow p-4">
        <div class="flex flex-col md:flex-row gap-4 items-end">
          <div>
            <div class="flex items-center gap-1 mb-2">
              <label class="block text-sm font-medium text-gray-700">
                Réseau
              </label>
              <div class="group relative">
                <svg class="w-4 h-4 text-gray-400 cursor-help" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
                </svg>
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-900 text-white text-xs rounded py-2 px-3 whitespace-nowrap z-10">
                  <div class="font-semibold mb-1">Filtrer par environnement</div>
                  <div>• Testnet: Binance testnet</div>
                  <div>• Live: Trading réel</div>
                  <div>• Paper: Simulation</div>
                  <div>• Backtest: Historique</div>
                </div>
              </div>
            </div>
            <select
              v-model="selectedEnvironment"
              class="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Tous</option>
              <option value="testnet">Testnet</option>
              <option value="live">Live</option>
              <option value="paper">Paper</option>
              <option value="backtest">Backtest</option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Période
            </label>
            <select
              v-model="selectedPeriod"
              class="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="day">Dernier 24h</option>
              <option value="month">Dernier mois</option>
              <option value="quarter">Dernier trimestre</option>
              <option value="year">Dernière année</option>
              <option value="custom">Personnalisé</option>
            </select>
          </div>

          <!-- Custom date range -->
          <div v-if="selectedPeriod === 'custom'" class="flex gap-4 flex-1">
            <div class="flex-1">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Du
              </label>
              <input
                v-model="customStartDate"
                type="date"
                class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div class="flex-1">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                Au
              </label>
              <input
                v-model="customEndDate"
                type="date"
                class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="isLoading" class="space-y-4">
        <div class="h-40 bg-gray-200 rounded animate-pulse"></div>
        <div class="h-40 bg-gray-200 rounded animate-pulse"></div>
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-lg p-4">
        <p class="text-red-800">{{ error }}</p>
      </div>

      <!-- Content -->
      <div v-else class="space-y-6">
        <!-- Global stats -->
        <PeriodStats title="Vue globale (tous les actifs)" :stats="globalStats" />

        <!-- Per-asset stats -->
        <div v-for="(assetStats, symbol) in assetStats" :key="symbol" class="space-y-2">
          <PeriodStats :title="`${symbol}`" :stats="assetStats" />
        </div>

        <!-- Empty state -->
        <div v-if="Object.keys(assetStats).length === 0" class="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
          <p class="text-gray-600">Aucun trade pour cette période</p>
        </div>
      </div>

      <!-- Optional Grafana link -->
      <div v-if="grafanaUrl" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="flex items-start">
          <svg
            class="flex-shrink-0 h-5 w-5 text-blue-400 mt-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clip-rule="evenodd"
            />
          </svg>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-blue-900">Visualisation avancée</h3>
            <p class="mt-1 text-sm text-blue-700">
              Accédez aux graphiques détaillés et analyses avancées dans
              <a
                :href="grafanaUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium underline hover:text-blue-800"
              >
                Grafana (hébergé séparément)
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import PeriodStats from '@/components/home/PeriodStats.vue'
import { getTrades, type Trade } from '@/api/trades'

type PeriodType = 'day' | 'month' | 'quarter' | 'year' | 'custom'

interface StatsData {
  pnl: number
  pnlPercent: number
  totalTrades: number
  winRate: number
  volumeTraded: number
}

const selectedPeriod = ref<PeriodType>('month')
const selectedEnvironment = ref<'testnet' | 'live' | 'paper' | 'backtest' | ''>('')
const customStartDate = ref('')
const customEndDate = ref('')
const trades = ref<Trade[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)

// Optional Grafana base URL from environment
const grafanaUrl = computed(() => import.meta.env.VITE_GRAFANA_BASE_URL)

// Get date range based on period
const getDateRange = () => {
  const now = new Date()
  const startDate = new Date()

  if (selectedPeriod.value === 'day') {
    startDate.setDate(startDate.getDate() - 1)
  } else if (selectedPeriod.value === 'month') {
    startDate.setDate(startDate.getDate() - 30)
  } else if (selectedPeriod.value === 'quarter') {
    startDate.setDate(startDate.getDate() - 90)
  } else if (selectedPeriod.value === 'year') {
    startDate.setDate(startDate.getDate() - 365)
  } else if (selectedPeriod.value === 'custom') {
    if (!customStartDate.value || !customEndDate.value) {
      return { startDate: new Date(0), endDate: now }
    }
    return {
      startDate: new Date(customStartDate.value),
      endDate: new Date(customEndDate.value)
    }
  }

  return { startDate, endDate: now }
}

// Filter trades by date range and environment
const filteredTrades = computed(() => {
  const { startDate, endDate } = getDateRange()

  return trades.value.filter((trade) => {
    const closedAt = new Date(trade.closed_at)
    const isInDateRange = closedAt >= startDate && closedAt <= endDate
    const isInEnvironment = !selectedEnvironment.value || trade.environment === selectedEnvironment.value
    return isInDateRange && isInEnvironment
  })
})

// Calculate global stats
const globalStats = computed<StatsData>(() => {
  if (filteredTrades.value.length === 0) {
    return {
      pnl: 0,
      pnlPercent: 0,
      totalTrades: 0,
      winRate: 0,
      volumeTraded: 0
    }
  }

  const pnl = filteredTrades.value.reduce((sum, trade) => sum + Number(trade.pnl), 0)
  const volumeTraded = filteredTrades.value.reduce(
    (sum, trade) => sum + Number(trade.entry_price) * Number(trade.quantity),
    0
  )
  const pnlPercent = volumeTraded > 0 ? (pnl / volumeTraded) * 100 : 0
  const winningTrades = filteredTrades.value.filter((trade) => Number(trade.pnl) > 0).length
  const winRate = (winningTrades / filteredTrades.value.length) * 100

  return {
    pnl,
    pnlPercent,
    totalTrades: filteredTrades.value.length,
    winRate,
    volumeTraded
  }
})

// Calculate per-asset stats
const assetStats = computed<Record<string, StatsData>>(() => {
  const bySymbol: Record<string, Trade[]> = {}

  filteredTrades.value.forEach((trade) => {
    if (!bySymbol[trade.symbol]) {
      bySymbol[trade.symbol] = []
    }
    bySymbol[trade.symbol].push(trade)
  })

  const result: Record<string, StatsData> = {}

  Object.entries(bySymbol).forEach(([symbol, symbolTrades]) => {
    if (symbolTrades.length === 0) {
      result[symbol] = {
        pnl: 0,
        pnlPercent: 0,
        totalTrades: 0,
        winRate: 0,
        volumeTraded: 0
      }
      return
    }

    const pnl = symbolTrades.reduce((sum, trade) => sum + Number(trade.pnl), 0)
    const volumeTraded = symbolTrades.reduce(
      (sum, trade) => sum + Number(trade.entry_price) * Number(trade.quantity),
      0
    )
    const pnlPercent = volumeTraded > 0 ? (pnl / volumeTraded) * 100 : 0
    const winningTrades = symbolTrades.filter((trade) => Number(trade.pnl) > 0).length
    const winRate = (winningTrades / symbolTrades.length) * 100

    result[symbol] = {
      pnl,
      pnlPercent,
      totalTrades: symbolTrades.length,
      winRate,
      volumeTraded
    }
  })

  return result
})

// Fetch trades
const fetchTrades = async () => {
  isLoading.value = true
  error.value = null
  try {
    const response = await getTrades({ limit: 1000, offset: 0 })
    trades.value = response.items
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch trades'
    console.error('Error fetching trades:', err)
  } finally {
    isLoading.value = false
  }
}

// Fetch trades on mount
onMounted(() => {
  fetchTrades()
})

// Watch for period changes
watch(selectedPeriod, () => {
  if (selectedPeriod.value !== 'custom') {
    customStartDate.value = ''
    customEndDate.value = ''
  }
})
</script>
