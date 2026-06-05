<template>
  <div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-xl font-semibold text-gray-900 mb-4">
      {{ title }}
    </h2>

    <!-- Loading state -->
    <div v-if="isLoading" class="space-y-3">
      <div class="h-6 bg-gray-200 rounded animate-pulse"></div>
      <div class="h-4 bg-gray-200 rounded animate-pulse w-2/3"></div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="p-3 bg-red-50 border border-red-200 rounded-md">
      <p class="text-xs text-red-800">{{ error }}</p>
    </div>

    <!-- P&L display -->
    <div v-else class="space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-600">P&L</span>
        <span :class="[
          'text-lg font-semibold',
          pnlValue >= 0 ? 'text-green-600' : 'text-red-600'
        ]">
          {{ formatCurrency(pnlValue) }}
        </span>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-600">Pourcentage</span>
        <span :class="[
          'text-sm font-medium',
          pnlPercent >= 0 ? 'text-green-600' : 'text-red-600'
        ]">
          {{ formatPercent(pnlPercent) }}
        </span>
      </div>

      <div class="flex items-center justify-between pt-3 border-t border-gray-200">
        <span class="text-sm text-gray-600">Trades</span>
        <span class="text-sm font-medium text-gray-900">{{ tradesCount }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { formatCurrency, formatPercent } from '@/utils/format'
import { getTrades, type Trade } from '@/api/trades'

interface Props {
  period: 'day' | 'week' | 'month'
}

const props = defineProps<Props>()

const trades = ref<Trade[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)

// Fetch all trades on mount
onMounted(async () => {
  isLoading.value = true
  error.value = null
  try {
    // Fetch all trades without limit for calculations
    const response = await getTrades({ limit: 1000, offset: 0 })
    trades.value = response.items
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch trades'
    console.error('Error fetching trades:', err)
  } finally {
    isLoading.value = false
  }
})

// Calculate P&L based on period
const filteredTrades = computed(() => {
  const now = new Date()
  const cutoffDate = new Date()

  if (props.period === 'day') {
    cutoffDate.setDate(cutoffDate.getDate() - 1)
  } else if (props.period === 'week') {
    cutoffDate.setDate(cutoffDate.getDate() - 7)
  } else if (props.period === 'month') {
    cutoffDate.setDate(cutoffDate.getDate() - 30)
  }

  return trades.value.filter((trade) => {
    const closedAt = new Date(trade.closed_at)
    return closedAt >= cutoffDate && closedAt <= now
  })
})

const pnlValue = computed(() => {
  return filteredTrades.value.reduce((sum, trade) => sum + Number(trade.pnl), 0)
})

const pnlPercent = computed(() => {
  if (filteredTrades.value.length === 0) return 0
  const totalInvested = filteredTrades.value.reduce((sum, trade) => {
    return sum + Number(trade.entry_price) * Number(trade.quantity)
  }, 0)
  if (totalInvested === 0) return 0
  return (pnlValue.value / totalInvested) * 100
})

const tradesCount = computed(() => {
  return filteredTrades.value.length
})

const title = computed(() => {
  const titles = {
    day: 'P&L Jour',
    week: 'P&L Semaine',
    month: 'P&L Mois',
  }
  return titles[props.period]
})
</script>
