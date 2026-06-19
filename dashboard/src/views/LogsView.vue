<template>
  <AppLayout>
    <div class="space-y-6">
      <!-- Page Header -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-gray-900">Logs & Erreurs</h1>
          <p class="mt-2 text-gray-600">Journaux système et erreurs du bot de trading</p>
        </div>
      </div>

      <!-- Statistics Cards -->
      <div v-if="!isLoading && logs.length > 0" class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">INFO</p>
          <p class="text-2xl font-bold text-green-600">{{ logSummary.info }}</p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">WARNING</p>
          <p class="text-2xl font-bold text-yellow-600">{{ logSummary.warning }}</p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">ERROR</p>
          <p class="text-2xl font-bold text-orange-600">{{ logSummary.error }}</p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-600 mb-1">CRITICAL</p>
          <p class="text-2xl font-bold text-red-600">{{ logSummary.critical }}</p>
        </div>
      </div>

      <!-- Filters -->
      <div class="bg-white rounded-lg shadow p-4">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <!-- Level Filter -->
          <div>
            <div class="flex items-center gap-1 mb-1">
              <label class="block text-sm font-medium text-gray-700">Niveau</label>
              <div class="group relative">
                <svg class="w-4 h-4 text-gray-400 cursor-help" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
                </svg>
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-gray-900 text-white text-xs rounded py-2 px-3 whitespace-nowrap z-10">
                  <div class="font-semibold mb-1">Filtrer par niveau de log</div>
                  <div>• INFO: Erreurs de faible gravité</div>
                  <div>• WARNING: Avertissements (gravité moyenne)</div>
                  <div>• ERROR: Erreurs (gravité élevée)</div>
                  <div>• CRITICAL: Erreurs critiques</div>
                </div>
              </div>
            </div>
            <select
              :value="filters.level || ''"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
              @change="setLevelFilter(($event.target as HTMLSelectElement).value || undefined)"
            >
              <option value="">Tous</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>

          <!-- Category Filter -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Catégorie</label>
            <input
              :value="filters.logger || ''"
              type="text"
              placeholder="Ex: exchange, strategy"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
              @input="filters.logger = ($event.target as HTMLInputElement).value || undefined"
            />
          </div>

          <!-- Search Filter -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Recherche</label>
            <input
              :value="filters.search || ''"
              type="text"
              placeholder="Rechercher dans les messages..."
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
              @input="setSearchFilter(($event.target as HTMLInputElement).value || undefined)"
            />
          </div>

          <!-- Action Buttons -->
          <div class="flex items-end gap-2">
            <button
              @click="applyFilters"
              class="flex-1 px-4 py-2 bg-primary-600 text-white rounded-md text-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              Filtrer
            </button>
            <button
              @click="clearFilters"
              class="px-4 py-2 border border-gray-300 text-gray-700 rounded-md text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              Réinitialiser
            </button>
          </div>
        </div>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Error Alert -->
      <ErrorAlert v-if="error" :message="error" @dismiss="error = null" />

      <!-- Empty State -->
      <EmptyState
        v-else-if="logs.length === 0"
        title="Aucun log trouvé"
        message="Aucun log ne correspond aux filtres sélectionnés."
      />

      <!-- Logs — card list (mobile) -->
      <div v-else class="md:hidden space-y-3">
        <div
          v-for="log in logs"
          :key="log.id"
          class="bg-white rounded-lg shadow p-4"
        >
          <div class="flex items-center justify-between mb-2">
            <span
              :class="[
                'px-2 py-1 rounded text-xs font-semibold',
                log.level === 'INFO'
                  ? 'bg-green-100 text-green-800'
                  : log.level === 'WARNING'
                  ? 'bg-yellow-100 text-yellow-800'
                  : log.level === 'ERROR'
                  ? 'bg-orange-100 text-orange-800'
                  : 'bg-red-100 text-red-800'
              ]"
            >
              {{ log.level }}
            </span>
            <span class="text-xs text-gray-500 whitespace-nowrap">{{ formatDateTime(log.timestamp) }}</span>
          </div>
          <p class="font-mono text-xs text-gray-700 mb-1">{{ log.logger }}</p>
          <p class="text-sm text-gray-900 break-words">{{ log.message }}</p>
        </div>
      </div>

      <!-- Logs Table (desktop) -->
      <div v-if="logs.length > 0" class="hidden md:block bg-white rounded-lg shadow overflow-hidden">
        <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-100 border-b">
            <tr>
              <th class="px-4 py-3 text-left font-semibold text-gray-900">Niveau</th>
              <th class="px-4 py-3 text-left font-semibold text-gray-900">Catégorie</th>
              <th class="px-4 py-3 text-left font-semibold text-gray-900">Message</th>
              <th class="px-4 py-3 text-left font-semibold text-gray-900">Timestamp</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="log in logs"
              :key="log.id"
              class="hover:bg-gray-50"
            >
              <!-- Level -->
              <td class="px-4 py-3">
                <span
                  :class="[
                    'px-2 py-1 rounded text-xs font-semibold',
                    log.level === 'INFO'
                      ? 'bg-green-100 text-green-800'
                      : log.level === 'WARNING'
                      ? 'bg-yellow-100 text-yellow-800'
                      : log.level === 'ERROR'
                      ? 'bg-orange-100 text-orange-800'
                      : 'bg-red-100 text-red-800'
                  ]"
                >
                  {{ log.level }}
                </span>
              </td>

              <!-- Category -->
              <td class="px-4 py-3 font-mono text-xs text-gray-700">
                {{ log.logger }}
              </td>

              <!-- Message -->
              <td class="px-4 py-3 text-gray-900 max-w-md">
                <div class="truncate" :title="log.message">
                  {{ log.message }}
                </div>
              </td>

              <!-- Timestamp -->
              <td class="px-4 py-3 text-gray-600 text-xs whitespace-nowrap">
                {{ formatDateTime(log.timestamp) }}
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="logs.length > 0" class="flex flex-col sm:flex-row items-center justify-center gap-3 sm:space-x-4">
        <span class="text-sm text-gray-700 order-first sm:order-none">
          Page {{ currentPage }} / {{ totalPages }}
          <span class="text-gray-500">({{ total }} logs)</span>
        </span>

        <div class="flex gap-2 w-full sm:w-auto">
          <button
            @click="handlePreviousPage"
            :disabled="offset === 0"
            class="flex-1 sm:flex-none px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Précédent
          </button>

          <button
            @click="handleNextPage"
            :disabled="!hasMore"
            class="flex-1 sm:flex-none px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Suivant
          </button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useLogsStore } from '@/stores/logs'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { formatDateTime } from '@/utils/format'

const logsStore = useLogsStore()

const isLoading = computed(() => logsStore.isLoading)
const logs = computed(() => logsStore.logs)
const error = computed(() => logsStore.error)
const filters = computed(() => logsStore.filters)
const logSummary = computed(() => logsStore.logSummary)
const isAutoRefreshing = computed(() => logsStore.isAutoRefreshing)
const currentPage = computed(() => logsStore.currentPage)
const totalPages = computed(() => logsStore.totalPages)
const total = computed(() => logsStore.total)
const hasMore = computed(() => logsStore.hasMore)
const offset = computed(() => logsStore.offset)

onMounted(async () => {
  await logsStore.fetchLogs()
  logsStore.startAutoRefresh(10000) // Auto-refresh every 10 seconds
})

onBeforeUnmount(() => {
  logsStore.stopAutoRefresh()
})

function setLevelFilter(level: string | undefined): void {
  logsStore.setLevelFilter(level)
}

function setSearchFilter(search: string | undefined): void {
  logsStore.setSearchFilter(search)
}

async function applyFilters(): Promise<void> {
  await logsStore.fetchLogs()
}

async function clearFilters(): Promise<void> {
  logsStore.clearFilters()
  await logsStore.fetchLogs()
}

function handleNextPage(): void {
  logsStore.nextPage()
  logsStore.fetchLogs()
}

function handlePreviousPage(): void {
  logsStore.previousPage()
  logsStore.fetchLogs()
}
</script>
