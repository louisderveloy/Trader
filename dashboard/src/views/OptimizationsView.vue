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

      <!-- Filter / Sort bar (applied server-side) -->
      <div class="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <!-- Symbol -->
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" title="Filtrer par paire de trading">
              Symbole
            </label>
            <select
              v-model="filterSymbol"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">Tous les symboles</option>
              <option v-for="sym in symbols" :key="sym" :value="sym">{{ sym }}</option>
            </select>
          </div>

          <!-- Objective -->
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" title="Filtrer par objectif d'optimisation">
              Objectif
            </label>
            <select
              v-model="filterObjective"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">Tous les objectifs</option>
              <option v-for="obj in objectiveOptions" :key="obj" :value="obj">
                {{ objectiveLabel(obj) }}
              </option>
            </select>
          </div>

          <!-- Status -->
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" title="Filtrer par statut d'exécution">
              Statut
            </label>
            <select
              v-model="filterStatus"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">Tous les statuts</option>
              <option v-for="st in statusOptions" :key="st" :value="st">{{ statusLabel(st) }}</option>
            </select>
          </div>

          <!-- Sort field -->
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" title="Champ utilisé pour le tri">
              Trier par
            </label>
            <select
              v-model="sortBy"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="completed_at">Date de fin</option>
              <option value="started_at">Date de début</option>
              <option value="best_value">Meilleur score</option>
            </select>
          </div>

          <!-- Sort direction -->
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" title="Ordre de tri croissant ou décroissant">
              Ordre
            </label>
            <select
              v-model="sortDir"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="desc">Décroissant</option>
              <option value="asc">Croissant</option>
            </select>
          </div>

          <!-- Active weights toggle -->
          <div class="flex items-end">
            <label
              class="inline-flex cursor-pointer items-center gap-2 text-sm font-medium text-gray-700"
              title="N'afficher que l'optimisation dont le jeu de poids est activé"
            >
              <input
                v-model="filterActiveOnly"
                type="checkbox"
                class="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              Jeu de poids activé uniquement
            </label>
          </div>
        </div>

        <!-- Results summary + reset -->
        <div class="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
          <p class="text-sm text-gray-500">{{ total }} résultat(s)</p>
          <button
            v-if="hasActiveFilters"
            @click="resetFilters"
            class="text-sm text-blue-600 hover:text-blue-800 hover:underline"
          >
            Réinitialiser les filtres
          </button>
        </div>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Optimizations Content -->
      <div v-else-if="optimizations.length > 0" class="space-y-6">
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

        <!-- Pagination (server-side) -->
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

      <!-- No results for current filters -->
      <EmptyState
        v-else-if="hasActiveFilters"
        title="Aucun résultat"
        description="Aucune optimisation ne correspond aux filtres sélectionnés"
        @action="resetFilters"
        action-label="Réinitialiser les filtres"
      />

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
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useOptimizationsStore } from '@/stores/optimizations'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LaunchOptimizationModal from '@/components/optimizations/LaunchOptimizationModal.vue'
import LogsModal from '@/components/runs/LogsModal.vue'
import OptimizationCard from '@/components/optimizations/OptimizationCard.vue'
import type { LaunchOptimizationRequest, OptimizationStatus } from '@/api/optimizations'

const optimizationsStore = useOptimizationsStore()
const auth = useAuthStore()

// Two-way bind the filter/sort controls directly to the store state.
const { filterSymbol, filterObjective, filterStatus, filterActiveOnly, sortBy, sortDir, symbols } =
  storeToRefs(optimizationsStore)

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

// Fixed option sets (objective enum is stable; status is the run lifecycle).
const statusOptions: OptimizationStatus[] = [
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
]
const objectiveOptions = [
  'sharpe_ratio',
  'sortino_ratio',
  'profit_factor',
  'win_rate',
  'total_return',
]

const statusLabels: Record<string, string> = {
  pending: 'En attente',
  running: 'En cours',
  completed: 'Terminé',
  failed: 'Échoué',
  cancelled: 'Annulé',
}
const objectiveLabels: Record<string, string> = {
  sharpe_ratio: 'Ratio de Sharpe',
  sortino_ratio: 'Ratio de Sortino',
  profit_factor: 'Facteur de profit',
  win_rate: 'Taux de réussite',
  total_return: 'Rendement total',
}

function statusLabel(status: string): string {
  return statusLabels[status] ?? status
}
function objectiveLabel(objective: string): string {
  return objectiveLabels[objective] ?? objective
}

const hasActiveFilters = computed(
  () =>
    filterSymbol.value !== '' ||
    filterObjective.value !== '' ||
    filterStatus.value !== '' ||
    filterActiveOnly.value
)

// Any filter or sort change re-runs the query from page 1 (server-side).
watch(
  [filterSymbol, filterObjective, filterStatus, filterActiveOnly, sortBy, sortDir],
  () => {
    optimizationsStore.applyFilters()
  }
)

function resetFilters(): void {
  filterSymbol.value = ''
  filterObjective.value = ''
  filterStatus.value = ''
  filterActiveOnly.value = false
  // The watcher above triggers a single refetch once Vue flushes the updates.
}

onMounted(async () => {
  // No polling: fetched once on mount; the user refreshes manually.
  await Promise.all([
    optimizationsStore.fetchSymbols(),
    optimizationsStore.fetchOptimizations(),
  ])
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
