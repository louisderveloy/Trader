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
          @click="showLaunchModal = true"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          Lancer Optimisation
        </button>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Error Alert -->
      <ErrorAlert v-if="error" :message="error" @dismiss="error = null" />

      <!-- Launch Modal -->
      <LaunchOptimizationModal
        v-if="showLaunchModal"
        :is-loading="isLaunching"
        @close="showLaunchModal = false"
        @launch="handleLaunchOptimization"
      />

      <!-- Optimizations Content -->
      <div v-else-if="optimizations.length > 0" class="space-y-6">
        <!-- Studies List -->
        <div class="space-y-4">
          <div
            v-for="study in optimizations"
            :key="study.id"
            class="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow cursor-pointer"
            @click="selectOptimization(study.id)"
          >
            <div class="flex items-start justify-between mb-4">
              <div class="flex-1">
                <h3 class="text-lg font-semibold text-gray-900">{{ study.name }}</h3>
                <p class="text-sm text-gray-500">ID: {{ study.id }} • {{ study.n_trials }} essais</p>
              </div>
              <span
                :class="[
                  'px-3 py-1 rounded-full text-xs font-medium',
                  study.status === 'completed'
                    ? 'bg-green-100 text-green-800'
                    : study.status === 'running'
                    ? 'bg-blue-100 text-blue-800'
                    : study.status === 'failed'
                    ? 'bg-red-100 text-red-800'
                    : 'bg-gray-100 text-gray-800'
                ]"
              >
                {{ study.status }}
              </span>
            </div>

            <!-- Study Details -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div>
                <p class="text-xs text-gray-600">Objectif</p>
                <p class="font-semibold text-gray-900">{{ study.objective }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-600">Meilleur Score</p>
                <p class="font-semibold text-gray-900">
                  {{ study.best_value !== null ? study.best_value.toFixed(4) : '—' }}
                </p>
              </div>
              <div>
                <p class="text-xs text-gray-600">Sampler</p>
                <p class="font-semibold text-gray-900">{{ study.sampler }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-600">Créée</p>
                <p class="font-semibold text-gray-900">{{ formatDate(study.created_at) }}</p>
              </div>
            </div>

            <!-- Best Parameters (if completed) -->
            <div v-if="study.best_params" class="bg-gray-50 rounded p-3">
              <p class="text-xs font-semibold text-gray-700 mb-2">Meilleurs paramètres:</p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div v-for="(value, key) in study.best_params" :key="key">
                  <span class="text-gray-600">{{ key }}:</span>
                  <span class="font-mono text-gray-900">{{ formatParamValue(value) }}</span>
                </div>
              </div>
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
        v-else
        title="Aucune optimisation"
        description="Lancez une nouvelle étude pour commencer"
        @action="showLaunchModal = true"
        action-label="Lancer Optimisation"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useOptimizationsStore } from '@/stores/optimizations'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LaunchOptimizationModal from '@/components/optimizations/LaunchOptimizationModal.vue'
import { formatDate } from '@/utils/format'

const optimizationsStore = useOptimizationsStore()

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

onMounted(async () => {
  await optimizationsStore.fetchOptimizations()
})

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

async function selectOptimization(studyId: number): Promise<void> {
  await optimizationsStore.fetchOptimization(studyId)
}

async function handleLaunchOptimization(data: {
  name: string
  objective: string
  n_trials: number
  n_jobs: number
}): Promise<void> {
  try {
    await optimizationsStore.launch({
      name: data.name,
      objective: data.objective as 'sharpe' | 'sortino' | 'profit_factor',
      n_trials: data.n_trials,
      n_jobs: data.n_jobs
    })
    showLaunchModal.value = false
  } catch (err) {
    // Error is set in store
  }
}
</script>
