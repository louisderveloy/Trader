<template>
  <AppLayout>
    <div class="max-w-6xl mx-auto">
      <!-- Page Header -->
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-gray-900">Optimisations</h1>
          <p class="mt-2 text-gray-600">Études Optuna et résultats d'optimisation</p>
        </div>
        <button
          v-if="isAdmin"
          @click="showLaunchModal = true"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          Lancer Optimisation
        </button>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Error Alert -->
      <ErrorAlert v-if="error" :message="error" @dismiss="clearError" />

      <!-- Launch Modal -->
      <LaunchOptimizationModal
        v-if="showLaunchModal"
        :is-loading="isLaunching"
        @close="showLaunchModal = false"
        @launch="handleLaunchOptimization"
      />

      <!-- Logs Modal -->
      <LogsModal v-if="logsRunId !== null" :run-id="logsRunId" @close="logsRunId = null" />

      <!-- Optimizations Content -->
      <div v-if="optimizations.length > 0" class="space-y-6">
        <!-- Studies List -->
        <div class="space-y-4">
          <div
            v-for="study in optimizations"
            :key="study.run_id"
            class="bg-white rounded-lg shadow p-6"
          >
            <div class="flex items-start justify-between mb-4">
              <div class="flex-1">
                <h3 class="text-lg font-semibold text-gray-900">{{ study.study_name }}</h3>
                <p class="text-sm text-gray-500">
                  Run #{{ study.run_id }} • {{ study.n_trials ?? '—' }} essais
                </p>
              </div>
              <span
                :class="[
                  'px-3 py-1 rounded-full text-xs font-medium',
                  study.status === 'completed'
                    ? 'bg-green-100 text-green-800'
                    : study.status === 'running' || study.status === 'pending'
                    ? 'bg-blue-100 text-blue-800'
                    : study.status === 'failed'
                    ? 'bg-red-100 text-red-800'
                    : 'bg-gray-100 text-gray-800',
                ]"
              >
                {{ study.status }}
              </span>
            </div>

            <!-- Study Details -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div>
                <p class="text-xs text-gray-600">Objectif</p>
                <p class="font-semibold text-gray-900">{{ study.objective ?? '—' }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-600">Meilleur Score</p>
                <p class="font-semibold text-gray-900">
                  {{ study.best_value !== null ? study.best_value.toFixed(4) : '—' }}
                </p>
              </div>
              <div>
                <p class="text-xs text-gray-600">Symbole</p>
                <p class="font-semibold text-gray-900">{{ study.symbol ?? '—' }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-600">Créée</p>
                <p class="font-semibold text-gray-900">{{ formatDate(study.created_at) }}</p>
              </div>
            </div>

            <!-- Best Parameters (if completed) -->
            <div v-if="study.best_params" class="bg-gray-50 rounded p-3 mb-4">
              <p class="text-xs font-semibold text-gray-700 mb-2">Meilleurs paramètres:</p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div v-for="(value, key) in study.best_params" :key="key">
                  <span class="text-gray-600">{{ key }}:</span>
                  <span class="font-mono text-gray-900">{{ formatParamValue(value) }}</span>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="pt-4 border-t border-gray-200 flex flex-wrap items-center gap-2">
              <button
                type="button"
                @click="logsRunId = study.run_id"
                class="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
              >
                Logs
              </button>
              <button
                v-if="isAdmin && isActive(study)"
                type="button"
                @click="handleStop(study.run_id)"
                class="px-3 py-1.5 text-sm border border-amber-300 rounded-md text-amber-800 bg-amber-50 hover:bg-amber-100"
              >
                Arrêter
              </button>
              <button
                v-if="isAdmin && isActive(study)"
                type="button"
                @click="handleKill(study.run_id)"
                class="px-3 py-1.5 text-sm border border-red-300 rounded-md text-red-800 bg-red-50 hover:bg-red-100"
              >
                Kill
              </button>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div class="flex items-center justify-between">
          <p class="text-sm text-gray-600">
            Page {{ currentPage }} de {{ totalPages }} ({{ total }} études)
          </p>
          <div class="flex gap-2">
            <button
              @click="handlePreviousPage"
              :disabled="!hasPrevious"
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

      <!-- Empty State -->
      <EmptyState
        v-else-if="!isLoading"
        title="Aucune optimisation"
        description="Lancez une nouvelle étude pour commencer"
        @action="showLaunchModal = true"
        action-label="Lancer Optimisation"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useOptimizationsStore } from '@/stores/optimizations'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LaunchOptimizationModal from '@/components/optimizations/LaunchOptimizationModal.vue'
import LogsModal from '@/components/runs/LogsModal.vue'
import type { Optimization, LaunchOptimizationRequest } from '@/api/optimizations'
import { formatDate } from '@/utils/format'

const optimizationsStore = useOptimizationsStore()
const auth = useAuthStore()

const isAdmin = computed(() => auth.isAdmin)
const isLoading = computed(() => optimizationsStore.isLoading)
const isLaunching = computed(() => optimizationsStore.isLaunching)
const optimizations = computed(() => optimizationsStore.optimizations)
const error = computed(() => optimizationsStore.error)
const currentPage = computed(() => optimizationsStore.currentPage)
const totalPages = computed(() => optimizationsStore.totalPages)
const total = computed(() => optimizationsStore.total)
const hasMore = computed(() => optimizationsStore.hasMore)
const hasPrevious = computed(() => optimizationsStore.offset > 0)

const showLaunchModal = ref(false)
const logsRunId = ref<number | null>(null)

onMounted(async () => {
  await optimizationsStore.fetchOptimizations()
  optimizationsStore.startPolling()
})

onUnmounted(() => {
  optimizationsStore.stopPolling()
})

function isActive(study: Optimization): boolean {
  return study.status === 'running' || study.status === 'pending'
}

function clearError(): void {
  optimizationsStore.error = null
}

function formatParamValue(value: unknown): string {
  if (typeof value === 'number') {
    return value.toFixed(4)
  }
  return String(value)
}

function handleNextPage(): void {
  optimizationsStore.nextPage()
  optimizationsStore.fetchOptimizations()
}

function handlePreviousPage(): void {
  optimizationsStore.previousPage()
  optimizationsStore.fetchOptimizations()
}

async function handleStop(runId: number): Promise<void> {
  await optimizationsStore.stopOptimization(runId)
}

async function handleKill(runId: number): Promise<void> {
  await optimizationsStore.killOptimization(runId)
}

async function handleLaunchOptimization(payload: LaunchOptimizationRequest): Promise<void> {
  const runId = await optimizationsStore.launch(payload)
  if (runId !== null) {
    showLaunchModal.value = false
  }
}
</script>
