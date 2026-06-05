<template>
  <div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-lg font-semibold text-gray-900 mb-4">
      {{ title }}
    </h2>

    <!-- Stats grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
      <!-- P&L in number -->
      <div class="border border-gray-200 rounded-lg p-4">
        <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">P&L</p>
        <p :class="[
          'text-2xl font-bold',
          stats.pnl >= 0 ? 'text-green-600' : 'text-red-600'
        ]">
          {{ formatCurrency(stats.pnl) }}
        </p>
        <p class="text-xs text-gray-600 mt-1">USDT</p>
      </div>

      <!-- P&L percentage -->
      <div class="border border-gray-200 rounded-lg p-4">
        <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">P&L %</p>
        <p :class="[
          'text-2xl font-bold',
          stats.pnlPercent >= 0 ? 'text-green-600' : 'text-red-600'
        ]">
          {{ formatPercent(stats.pnlPercent) }}
        </p>
        <p class="text-xs text-gray-600 mt-1">Rendement</p>
      </div>

      <!-- Total trades -->
      <div class="border border-gray-200 rounded-lg p-4">
        <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Trades</p>
        <p class="text-2xl font-bold text-gray-900">
          {{ stats.totalTrades }}
        </p>
        <p class="text-xs text-gray-600 mt-1">Nombre total</p>
      </div>

      <!-- Win rate -->
      <div class="border border-gray-200 rounded-lg p-4">
        <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Win rate</p>
        <p :class="[
          'text-2xl font-bold',
          stats.winRate >= 50 ? 'text-green-600' : 'text-red-600'
        ]">
          {{ formatPercent(stats.winRate) }}
        </p>
        <p class="text-xs text-gray-600 mt-1">Trades gagnants</p>
      </div>

      <!-- Volume traded -->
      <div class="border border-gray-200 rounded-lg p-4">
        <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Volume</p>
        <p class="text-2xl font-bold text-gray-900">
          {{ formatVolume(stats.volumeTraded) }}
        </p>
        <p class="text-xs text-gray-600 mt-1">USDT</p>
      </div>

      <!-- Average P&L per trade -->
      <div class="border border-gray-200 rounded-lg p-4">
        <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Avg. P&L</p>
        <p :class="[
          'text-2xl font-bold',
          avgPnlPerTrade >= 0 ? 'text-green-600' : 'text-red-600'
        ]">
          {{ formatCurrency(avgPnlPerTrade) }}
        </p>
        <p class="text-xs text-gray-600 mt-1">Par trade</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatCurrency, formatPercent } from '@/utils/format'

interface Stats {
  pnl: number
  pnlPercent: number
  totalTrades: number
  winRate: number
  volumeTraded: number
}

interface Props {
  title: string
  stats: Stats
}

const props = defineProps<Props>()

// Format volume with K/M suffixes
function formatVolume(value: number): string {
  if (value >= 1_000_000) {
    return (value / 1_000_000).toFixed(2) + 'M'
  } else if (value >= 1_000) {
    return (value / 1_000).toFixed(2) + 'K'
  }
  return value.toFixed(2)
}

// Calculate average P&L per trade
const avgPnlPerTrade = computed(() => {
  if (props.stats.totalTrades === 0) return 0
  return props.stats.pnl / props.stats.totalTrades
})
</script>
