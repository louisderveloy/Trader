<template>
  <div class="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow">
    <!-- Header -->
    <div class="flex items-start justify-between mb-4">
      <div class="flex-1">
        <h3 class="text-lg font-semibold text-gray-900">{{ optimization.study_name }}</h3>
        <p class="text-sm text-gray-500">
          Run #{{ optimization.run_id }} • {{ optimization.n_trials ?? '—' }} essais
        </p>
      </div>
      <RunStatusBadge :status="optimization.status" />
    </div>

    <!-- Details -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
      <div>
        <p class="text-xs text-gray-600">Objectif</p>
        <p class="font-semibold text-gray-900">{{ optimization.objective ?? '—' }}</p>
      </div>
      <div>
        <p class="text-xs text-gray-600">Meilleur Score</p>
        <p class="font-semibold text-gray-900">
          {{ optimization.best_value !== null ? optimization.best_value.toFixed(4) : '—' }}
        </p>
      </div>
      <div>
        <p class="text-xs text-gray-600">Symbole</p>
        <p class="font-semibold text-gray-900">{{ optimization.symbol ?? '—' }}</p>
      </div>
      <div>
        <p class="text-xs text-gray-600">Créée</p>
        <p class="font-semibold text-gray-900">{{ formatDate(optimization.created_at) }}</p>
      </div>
    </div>

    <!-- Best parameters (once completed) -->
    <div v-if="optimization.best_params" class="bg-gray-50 rounded p-3 mb-4">
      <p class="text-xs font-semibold text-gray-700 mb-2">Meilleurs paramètres:</p>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
        <div v-for="(value, key) in optimization.best_params" :key="key">
          <span class="text-gray-600">{{ key }}:</span>
          <span class="font-mono text-gray-900">{{ formatParamValue(value) }}</span>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="pt-4 border-t border-gray-200 flex flex-wrap items-center gap-2">
      <button
        type="button"
        @click="$emit('logs', optimization.run_id)"
        class="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
      >
        Logs
      </button>

      <!-- Stop/Kill are admin-only and only while active. Killing an optimization
           is safe (no exchange positions), so both are offered. -->
      <button
        v-if="canControl"
        type="button"
        @click="$emit('stop', optimization.run_id)"
        class="px-3 py-1.5 text-sm border border-amber-300 rounded-md text-amber-800 bg-amber-50 hover:bg-amber-100"
      >
        Arrêter
      </button>
      <button
        v-if="canControl"
        type="button"
        @click="$emit('kill', optimization.run_id)"
        class="px-3 py-1.5 text-sm border border-red-300 rounded-md text-red-800 bg-red-50 hover:bg-red-100"
      >
        Kill
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Optimization } from '@/api/optimizations'
import RunStatusBadge from '@/components/runs/RunStatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDate } from '@/utils/format'

interface Props {
  optimization: Optimization
}

const props = defineProps<Props>()

defineEmits<{
  logs: [runId: number]
  stop: [runId: number]
  kill: [runId: number]
}>()

const auth = useAuthStore()

const isActive = computed(
  () => props.optimization.status === 'running' || props.optimization.status === 'pending'
)
const canControl = computed(() => auth.isAdmin && isActive.value)

function formatParamValue(value: unknown): string {
  if (typeof value === 'number') {
    return value.toFixed(4)
  }
  return String(value)
}
</script>
