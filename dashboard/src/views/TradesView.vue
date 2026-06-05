<template>
  <AppLayout>
    <div class="max-w-7xl mx-auto">
      <!-- Page Header -->
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-gray-900">Historique des Trades</h1>
        <p class="mt-2 text-gray-600">Analyse et historique des transactions complétées</p>
      </div>

      <!-- Statistics Cards -->
      <div v-if="!isLoading && trades.length > 0" class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">Total Trades</p>
          <p class="text-2xl font-bold text-gray-900">{{ stats.totalTrades }}</p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">Win Rate</p>
          <p class="text-2xl font-bold" :class="stats.winRate >= 50 ? 'text-green-600' : 'text-red-600'">
            {{ stats.winRate.toFixed(1) }}%
          </p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">Total P&L</p>
          <p class="text-2xl font-bold" :class="Number(stats.totalPnl) >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ Number(stats.totalPnl).toFixed(2) }} USDT
          </p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">Avg P&L</p>
          <p class="text-2xl font-bold" :class="Number(stats.avgPnl) >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ Number(stats.avgPnl).toFixed(2) }} USDT
          </p>
        </div>
      </div>

      <!-- Filters -->
      <div class="bg-white rounded-lg shadow p-4 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <div class="flex items-center gap-1 mb-1">
              <label class="block text-sm font-medium text-gray-700">Réseau</label>
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
              :value="filters.environment || ''"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @change="updateFilter('environment', ($event.target.value as 'testnet' | 'live' | 'paper' | 'backtest') || undefined)"
            >
              <option value="">Tous</option>
              <option value="testnet">Testnet</option>
              <option value="live">Live</option>
              <option value="paper">Paper</option>
              <option value="backtest">Backtest</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Symbole</label>
            <input
              :value="filters.symbol || ''"
              type="text"
              placeholder="Ex: BTCUSDT"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @input="updateFilter('symbol', $event.target.value || undefined)"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Side</label>
            <select
              :value="filters.side || ''"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @change="updateFilter('side', ($event.target.value as 'long' | 'short') || undefined)"
            >
              <option value="">Tous</option>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Min P&L</label>
            <input
              :value="filters.min_pnl || ''"
              type="number"
              placeholder="Min"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @input="updateFilter('min_pnl', $event.target.value ? parseFloat($event.target.value) : undefined)"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Max P&L</label>
            <input
              :value="filters.max_pnl || ''"
              type="number"
              placeholder="Max"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @input="updateFilter('max_pnl', $event.target.value ? parseFloat($event.target.value) : undefined)"
            />
          </div>
        </div>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Error Alert -->
      <ErrorAlert v-if="error" :message="error" @dismiss="error = null" />

      <!-- Trades Table -->
      <div v-else-if="trades.length > 0" class="bg-white rounded-lg shadow overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-100 border-b">
            <tr>
              <th class="px-4 py-3 text-left font-semibold text-gray-900">Symbole</th>
              <th class="px-4 py-3 text-left font-semibold text-gray-900">Side</th>
              <th class="px-4 py-3 text-right font-semibold text-gray-900">Entrée</th>
              <th class="px-4 py-3 text-right font-semibold text-gray-900">Sortie</th>
              <th class="px-4 py-3 text-right font-semibold text-gray-900">P&L</th>
              <th class="px-4 py-3 text-center font-semibold text-gray-900">%</th>
              <th class="px-4 py-3 text-right font-semibold text-gray-900">Durée</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="trade in trades" :key="trade.id" class="hover:bg-gray-50">
              <td class="px-4 py-3 font-medium text-gray-900">{{ trade.symbol }}</td>
              <td class="px-4 py-3">
                <span
                  :class="[
                    'px-2 py-1 rounded text-xs font-medium',
                    trade.side === 'long' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  ]"
                >
                  {{ trade.side.toUpperCase() }}
                </span>
              </td>
              <td class="px-4 py-3 text-right text-gray-700">
                {{ Number(trade.entry_price).toFixed(2) }}
              </td>
              <td class="px-4 py-3 text-right text-gray-700">
                {{ Number(trade.exit_price).toFixed(2) }}
              </td>
              <td class="px-4 py-3 text-right font-semibold" :class="getPnlColor(Number(trade.pnl))">
                {{ Number(trade.pnl).toFixed(2) }} USDT
              </td>
              <td class="px-4 py-3 text-center font-semibold" :class="getPnlColor(Number(trade.pnl_percent) * 100)">
                {{ (Number(trade.pnl_percent) * 100).toFixed(2) }}%
              </td>
              <td class="px-4 py-3 text-gray-700 text-sm">
                {{ formatDuration(trade.duration_seconds) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Empty State -->
      <EmptyState
        v-else
        title="Aucun trade"
        description="Aucun trade ne correspond aux filtres"
      />

      <!-- Pagination -->
      <div v-if="trades.length > 0" class="flex items-center justify-between mt-6">
        <p class="text-sm text-gray-600">
          Page {{ currentPage }} de {{ totalPages }} ({{ total }} trades)
        </p>
        <div class="flex gap-2">
          <button
            @click="handlePreviousPage"
            :disabled="offset === 0"
            class="px-4 py-2 border border-gray-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
          >
            Précédent
          </button>
          <button
            @click="handleNextPage"
            :disabled="!hasMore"
            class="px-4 py-2 border border-gray-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
          >
            Suivant
          </button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTradesStore } from '@/stores/trades'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const tradesStore = useTradesStore()

const isLoading = computed(() => tradesStore.isLoading)
const trades = computed(() => tradesStore.trades)
const error = computed(() => tradesStore.error)
const filters = computed(() => tradesStore.filters)
const stats = computed(() => tradesStore.stats)
const currentPage = computed(() => tradesStore.currentPage)
const totalPages = computed(() => tradesStore.totalPages)
const total = computed(() => tradesStore.total)
const hasMore = computed(() => tradesStore.hasMore)
const offset = computed(() => tradesStore.offset)

onMounted(async () => {
  await tradesStore.fetchTrades()
})

function updateFilter(key: string, value: unknown) {
  tradesStore.setFilters({ [key]: value })
  tradesStore.fetchTrades()
}

function handleNextPage(): void {
  tradesStore.nextPage()
  tradesStore.fetchTrades()
}

function handlePreviousPage(): void {
  tradesStore.previousPage()
  tradesStore.fetchTrades()
}

function getPnlColor(pnl: number | null | undefined): string {
  if (pnl === null || pnl === undefined) return 'text-gray-700'
  const numPnl = Number(pnl)
  return numPnl >= 0 ? 'text-green-600' : 'text-red-600'
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m`
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`
  } else {
    return `${secs}s`
  }
}
</script>
