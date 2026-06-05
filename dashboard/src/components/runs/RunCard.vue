<template>
  <div class="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center space-x-3">
        <h3 class="text-lg font-semibold text-gray-900">
          {{ RUN_TYPE_CONFIG[run.run_type as RunType]?.label || run.run_type }}
        </h3>
        <RunStatusBadge :status="run.status" />
      </div>
      <span class="text-sm text-gray-500">#{{ run.id }}</span>
    </div>

    <!-- Info grid -->
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
      <!-- Symbol & Timeframe -->
      <div>
        <p class="text-gray-500">Symbol</p>
        <p class="font-medium text-gray-900">{{ run.symbol }}</p>
      </div>

      <div>
        <p class="text-gray-500">Timeframe</p>
        <p class="font-medium text-gray-900">{{ run.timeframe }}</p>
      </div>

      <div>
        <p class="text-gray-500">Environment</p>
        <p class="font-medium text-gray-900 capitalize">{{ run.environment }}</p>
      </div>

      <!-- Dates -->
      <div>
        <p class="text-gray-500">Créé</p>
        <p class="font-medium text-gray-900">{{ formatDateShort(run.created_at) }}</p>
      </div>

      <div v-if="run.started_at">
        <p class="text-gray-500">Démarré</p>
        <p class="font-medium text-gray-900">{{ formatDateShort(run.started_at) }}</p>
      </div>

      <div v-if="run.completed_at">
        <p class="text-gray-500">Terminé</p>
        <p class="font-medium text-gray-900">{{ formatDateShort(run.completed_at) }}</p>
      </div>
    </div>

    <!-- Result (if completed) -->
    <div v-if="run.result && run.status === 'completed'" class="mt-4 pt-4 border-t border-gray-200">
      <p class="text-xs text-gray-500 mb-2">Résultats:</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div v-for="(value, key) in displayedResults" :key="key">
          <p class="text-gray-500 capitalize">{{ formatKey(key) }}</p>
          <p class="font-medium text-gray-900">{{ formatValue(value) }}</p>
        </div>
      </div>
    </div>

    <!-- Optional Grafana link -->
    <div v-if="grafanaUrl" class="mt-4 pt-4 border-t border-gray-200">
      <a
        :href="`${grafanaUrl}/d/run-detail?run_id=${run.id}`"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center text-sm text-primary-600 hover:text-primary-700"
      >
        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
          />
        </svg>
        Voir dans Grafana
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Run } from '@/api/types'
import RunStatusBadge from './RunStatusBadge.vue'
import { formatDateShort } from '@/utils/format'
import { RUN_TYPE_CONFIG } from '@/utils/constants'
import type { RunType } from '@/utils/constants'

interface Props {
  run: Run
}

const props = defineProps<Props>()

const grafanaUrl = computed(() => import.meta.env.VITE_GRAFANA_BASE_URL)

// Display only first 4 result keys
const displayedResults = computed(() => {
  if (!props.run.result) return {}
  const entries = Object.entries(props.run.result).slice(0, 4)
  return Object.fromEntries(entries)
})

function formatKey(key: string): string {
  return key.replace(/_/g, ' ')
}

function formatValue(value: any): string {
  if (typeof value === 'number') {
    return value.toFixed(2)
  }
  if (typeof value === 'boolean') {
    return value ? 'Oui' : 'Non'
  }
  return String(value)
}
</script>
