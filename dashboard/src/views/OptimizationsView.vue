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
          <OptimizationCard
            v-for="study in optimizations"
            :key="study.run_id"
            :optimization="study"
            @logs="openLogs"
            @stop="handleStop"
            @kill="handleKill"
            @activate-weights="handleActivateWeights"
          />
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
import { computed, onMounted, ref } from 'vue'
import { useOptimizationsStore } from '@/stores/optimizations'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LaunchOptimizationModal from '@/components/optimizations/LaunchOptimizationModal.vue'
import LogsModal from '@/components/runs/LogsModal.vue'
import OptimizationCard from '@/components/optimizations/OptimizationCard.vue'
import type { LaunchOptimizationRequest } from '@/api/optimizations'

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
  // No polling: the list is fetched once on mount; the user refreshes manually.
  await optimizationsStore.fetchOptimizations()
})

function clearError(): void {
  optimizationsStore.error = null
}

function openLogs(runId: number): void {
  logsRunId.value = runId
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

async function handleActivateWeights(runId: number): Promise<void> {
  await optimizationsStore.activateWeights(runId)
}

async function handleLaunchOptimization(payload: LaunchOptimizationRequest): Promise<void> {
  const runId = await optimizationsStore.launch(payload)
  if (runId !== null) {
    showLaunchModal.value = false
  }
}
</script>
