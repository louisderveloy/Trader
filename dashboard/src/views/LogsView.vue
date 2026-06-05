<template>
  <AppLayout>
    <div class="max-w-7xl mx-auto">
      <!-- Page Header -->
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-gray-900">Logs</h1>
          <p class="mt-2 text-gray-600">Journaux système et erreurs</p>
        </div>
        <button
          @click="toggleAutoRefresh"
          :class="[
            'px-4 py-2 rounded-md transition-colors',
            isAutoRefreshing
              ? 'bg-green-600 text-white hover:bg-green-700'
              : 'bg-gray-300 text-gray-700 hover:bg-gray-400'
          ]"
        >
          {{ isAutoRefreshing ? 'Auto-refresh ON' : 'Auto-refresh OFF' }}
        </button>
      </div>

      <!-- Log Summary -->
      <div v-if="!isLoading && logs.length > 0" class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <div class="bg-blue-50 rounded-lg p-3">
          <p class="text-xs text-blue-700 font-semibold">DEBUG</p>
          <p class="text-2xl font-bold text-blue-900">{{ logSummary.debug }}</p>
        </div>
        <div class="bg-green-50 rounded-lg p-3">
          <p class="text-xs text-green-700 font-semibold">INFO</p>
          <p class="text-2xl font-bold text-green-900">{{ logSummary.info }}</p>
        </div>
        <div class="bg-yellow-50 rounded-lg p-3">
          <p class="text-xs text-yellow-700 font-semibold">WARNING</p>
          <p class="text-2xl font-bold text-yellow-900">{{ logSummary.warning }}</p>
        </div>
        <div class="bg-orange-50 rounded-lg p-3">
          <p class="text-xs text-orange-700 font-semibold">ERROR</p>
          <p class="text-2xl font-bold text-orange-900">{{ logSummary.error }}</p>
        </div>
        <div class="bg-red-50 rounded-lg p-3">
          <p class="text-xs text-red-700 font-semibold">CRITICAL</p>
          <p class="text-2xl font-bold text-red-900">{{ logSummary.critical }}</p>
        </div>
      </div>

      <!-- Filters -->
      <div class="bg-white rounded-lg shadow p-4 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Niveau</label>
            <select
              :value="filters.level || ''"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @change="setLevelFilter(($event.target.value as string) || undefined)"
            >
              <option value="">Tous</option>
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Logger</label>
            <input
              :value="filters.logger || ''"
              type="text"
              placeholder="Ex: bot.exchange"
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @input="filters.logger = $event.target.value || undefined"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Recherche</label>
            <input
              :value="filters.search || ''"
              type="text"
              placeholder="Rechercher dans les messages..."
              class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              @input="setSearchFilter($event.target.value || undefined)"
            />
          </div>
        </div>
        <div class="mt-3 flex gap-2">
          <button
            @click="applyFilters"
            class="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
          >
            Filtrer
          </button>
          <button
            @click="clearFilters"
            class="px-4 py-2 bg-gray-300 text-gray-700 rounded-md text-sm hover:bg-gray-400"
          >
            Réinitialiser
          </button>
        </div>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Error Alert -->
      <ErrorAlert v-if="error" :message="error" @dismiss="error = null" />

      <!-- Logs List -->
      <div v-else-if="logs.length > 0" class="space-y-3">
        <div
          v-for="log in logs"
          :key="log.id"
          :class="[
            'rounded-lg p-4 border-l-4',
            log.level === 'DEBUG'
              ? 'bg-blue-50 border-blue-400'
              : log.level === 'INFO'
              ? 'bg-green-50 border-green-400'
              : log.level === 'WARNING'
              ? 'bg-yellow-50 border-yellow-400'
              : log.level === 'ERROR'
              ? 'bg-orange-50 border-orange-400'
              : 'bg-red-50 border-red-400'
          ]"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <span
                  :class="[
                    'px-2 py-1 rounded text-xs font-bold',
                    log.level === 'DEBUG'
                      ? 'bg-blue-200 text-blue-800'
                      : log.level === 'INFO'
                      ? 'bg-green-200 text-green-800'
                      : log.level === 'WARNING'
                      ? 'bg-yellow-200 text-yellow-800'
                      : log.level === 'ERROR'
                      ? 'bg-orange-200 text-orange-800'
                      : 'bg-red-200 text-red-800'
                  ]"
                >
                  {{ log.level }}
                </span>
                <span class="text-xs font-mono text-gray-700">{{ log.logger }}</span>
              </div>
              <p class="text-sm text-gray-900 mb-2">{{ log.message }}</p>
              <div class="flex flex-wrap gap-2 text-xs text-gray-600">
                <span v-if="log.source" class="bg-gray-200 px-2 py-1 rounded">
                  Source: {{ log.source }}
                </span>
                <span v-if="log.run_id" class="bg-gray-200 px-2 py-1 rounded">
                  Run: {{ log.run_id }}
                </span>
                <span class="bg-gray-200 px-2 py-1 rounded">
                  {{ formatDateTime(log.timestamp) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <EmptyState v-else title="Aucun log" description="Aucun log disponible" />

      <!-- Pagination -->
      <div v-if="logs.length > 0" class="flex items-center justify-between mt-6">
        <p class="text-sm text-gray-600">
          Page {{ currentPage }} de {{ totalPages }} ({{ total }} logs)
        </p>
        <div class="flex gap-2">
          <button
            @click="handlePreviousPage"
            :disabled="offset === 0"
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
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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
  logsStore.startAutoRefresh(5000)
})

onBeforeUnmount(() => {
  logsStore.stopAutoRefresh()
})

function toggleAutoRefresh(): void {
  if (isAutoRefreshing.value) {
    logsStore.stopAutoRefresh()
  } else {
    logsStore.startAutoRefresh(5000)
  }
}

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
