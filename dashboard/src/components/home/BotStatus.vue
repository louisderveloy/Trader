<template>
  <div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-xl font-semibold text-gray-900 mb-4">État du Bot</h2>

    <!-- Loading state -->
    <div v-if="runsStore.isLoading" class="text-center py-8">
      <LoadingSpinner />
    </div>

    <!-- Active runs -->
    <div v-else-if="runsStore.activeRuns.length > 0" class="space-y-3">
      <div
        v-for="run in runsStore.activeRuns"
        :key="run.id"
        class="p-3 bg-gray-50 rounded-md border border-gray-200"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-gray-700">
            {{ RUN_TYPE_CONFIG[run.run_type as RunType]?.label || run.run_type }}
          </span>
          <RunStatusBadge :status="run.status" />
        </div>

        <div class="text-sm text-gray-600 space-y-1">
          <p>{{ run.symbol }} - {{ run.timeframe }}</p>
          <p class="text-xs text-gray-500">
            Démarré {{ formatRelativeTime(run.started_at || run.created_at) }}
          </p>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="text-center py-8">
      <svg
        class="mx-auto h-12 w-12 text-gray-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
        />
      </svg>
      <p class="mt-2 text-sm text-gray-500">Aucun run actif</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRunsStore } from '@/stores/runs'
import RunStatusBadge from '@/components/runs/RunStatusBadge.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import { formatRelativeTime } from '@/utils/format'
import { RUN_TYPE_CONFIG, POLLING_INTERVALS } from '@/utils/constants'
import type { RunType } from '@/utils/constants'

const runsStore = useRunsStore()

onMounted(() => {
  // Start polling for active runs (every 10 seconds)
  runsStore.startPolling(POLLING_INTERVALS.ACTIVE_RUNS)
})

onUnmounted(() => {
  // Stop polling when component unmounts
  runsStore.stopPolling()
})
</script>
