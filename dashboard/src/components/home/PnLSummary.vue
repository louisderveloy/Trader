<template>
  <div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-xl font-semibold text-gray-900 mb-4">
      {{ title }}
    </h2>

    <!-- Placeholder data note -->
    <div class="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
      <p class="text-xs text-yellow-800">
        <strong>Wave 1:</strong> Données placeholder. P&L réel disponible en Wave 3 (endpoint /trades requis).
      </p>
    </div>

    <!-- P&L display -->
    <div class="space-y-3">
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
import { computed } from 'vue'
import { formatCurrency, formatPercent } from '@/utils/format'

interface Props {
  period: 'day' | 'week' | 'month'
}

const props = defineProps<Props>()

// Placeholder data for Wave 1
// In Wave 3, this will be fetched from /trades endpoint
const pnlValue = computed(() => {
  // Mock data based on period
  return props.period === 'day' ? 145.67 : props.period === 'week' ? 892.34 : 3241.89
})

const pnlPercent = computed(() => {
  return props.period === 'day' ? 1.46 : props.period === 'week' ? 8.92 : 32.42
})

const tradesCount = computed(() => {
  return props.period === 'day' ? 3 : props.period === 'week' ? 12 : 45
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
