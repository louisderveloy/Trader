<template>
  <AppLayout>
    <div class="space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <h1 class="text-3xl font-bold text-gray-900">Runs</h1>
        <button
          v-if="authStore.isAdmin"
          @click="showStartModal = true"
          class="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          Démarrer un run
        </button>
      </div>

      <!-- Filters -->
      <div class="bg-white rounded-lg shadow p-4">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <!-- Run type filter -->
          <div>
            <label for="filter-type" class="block text-sm font-medium text-gray-700 mb-1">
              Type
            </label>
            <select
              id="filter-type"
              v-model="filters.run_type"
              class="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Tous</option>
              <option value="backtest">Backtest</option>
              <option value="paper">Paper Trading</option>
              <option value="live">Live</option>
            </select>
          </div>

          <!-- Status filter -->
          <div>
            <label for="filter-status" class="block text-sm font-medium text-gray-700 mb-1">
              Status
            </label>
            <select
              id="filter-status"
              v-model="filters.status"
              class="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Tous</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          <!-- Symbol filter -->
          <div>
            <label for="filter-symbol" class="block text-sm font-medium text-gray-700 mb-1">
              Symbol
            </label>
            <input
              id="filter-symbol"
              v-model="filters.symbol"
              type="text"
              placeholder="BTCUSDT"
              class="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <!-- Apply button -->
          <div class="flex items-end">
            <button
              @click="applyFilters"
              class="w-full px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              Filtrer
            </button>
          </div>
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="runsStore.isLoading" class="text-center py-12">
        <LoadingSpinner size="lg" />
      </div>

      <!-- Error state -->
      <ErrorAlert v-else-if="runsStore.error" :message="runsStore.error" />

      <!-- Empty state -->
      <EmptyState
        v-else-if="visibleRuns.length === 0"
        title="Aucun run trouvé"
        message="Aucun run ne correspond aux filtres sélectionnés."
      />

      <!-- Runs list -->
      <div v-else class="space-y-4">
        <RunCard
          v-for="run in visibleRuns"
          :key="run.id"
          :run="run"
          @logs="openLogs"
          @stop="handleStop"
          @kill="handleKill"
        />
      </div>

      <!-- Pagination -->
      <div v-if="runsStore.runs.length > 0" class="flex items-center justify-center space-x-4">
        <button
          @click="runsStore.previousPage"
          :disabled="runsStore.offset === 0"
          class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Précédent
        </button>

        <span class="text-sm text-gray-700">
          Page {{ currentPage }} / {{ totalPages }}
          <span class="text-gray-500">({{ runsStore.total }} runs)</span>
        </span>

        <button
          @click="runsStore.nextPage"
          :disabled="!hasNextPage"
          class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Suivant
        </button>
      </div>
    </div>

    <!-- Start run modal -->
    <StartRunModal
      v-if="showStartModal"
      :is-loading="isStarting"
      @close="showStartModal = false"
      @launch="handleStart"
    />

    <!-- Logs modal -->
    <LogsModal
      v-if="logsRunId !== null"
      :run-id="logsRunId"
      @close="logsRunId = null"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRunsStore } from '@/stores/runs'
import { useAuthStore } from '@/stores/auth'
import type { StartRunRequest } from '@/api/types'
import AppLayout from '@/components/layout/AppLayout.vue'
import RunCard from '@/components/runs/RunCard.vue'
import StartRunModal from '@/components/runs/StartRunModal.vue'
import LogsModal from '@/components/runs/LogsModal.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const runsStore = useRunsStore()
const authStore = useAuthStore()

const filters = ref({
  run_type: '',
  status: '',
  symbol: '',
})

const showStartModal = ref(false)
const isStarting = ref(false)
const logsRunId = ref<number | null>(null)

// Optimization runs have a dedicated page; never show them here.
const visibleRuns = computed(() =>
  runsStore.runs.filter((run) => run.run_type !== 'optimization')
)

const currentPage = computed(() => Math.floor(runsStore.offset / runsStore.limit) + 1)
const totalPages = computed(() => Math.ceil(runsStore.total / runsStore.limit))
const hasNextPage = computed(() => runsStore.offset + runsStore.limit < runsStore.total)

function applyFilters() {
  // Reset offset when applying new filters
  runsStore.offset = 0
  runsStore.fetchRuns({
    run_type: filters.value.run_type || undefined,
    status: filters.value.status || undefined,
    symbol: filters.value.symbol || undefined,
  })
}

async function handleStart(payload: StartRunRequest) {
  isStarting.value = true
  try {
    const runId = await runsStore.startRun(payload)
    if (runId !== null) showStartModal.value = false
  } finally {
    isStarting.value = false
  }
}

function openLogs(runId: number) {
  logsRunId.value = runId
}

async function handleStop(runId: number) {
  if (!window.confirm(`Arrêter le run #${runId} ? Les positions ouvertes seront fermées proprement.`)) {
    return
  }
  await runsStore.stopRun(runId)
}

async function handleKill(runId: number) {
  if (!window.confirm(`Tuer (SIGKILL) le run #${runId} ? À utiliser uniquement pour les backtests.`)) {
    return
  }
  await runsStore.killRun(runId)
}

onMounted(() => {
  // Fetch runs on mount
  runsStore.fetchRuns()
})
</script>
