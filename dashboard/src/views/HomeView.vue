<template>
  <AppLayout>
    <div class="space-y-6">
      <h1 class="text-3xl font-bold text-gray-900">Tableau de bord</h1>

      <!-- Cards grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <BotStatus />
        <PnLSummary period="day" />
        <PnLSummary period="week" />
      </div>

      <!-- Optional Grafana link -->
      <div v-if="grafanaUrl" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="flex items-start">
          <svg
            class="flex-shrink-0 h-5 w-5 text-blue-400 mt-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clip-rule="evenodd"
            />
          </svg>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-blue-900">Visualisation avancée</h3>
            <p class="mt-1 text-sm text-blue-700">
              Accédez aux graphiques détaillés et analyses avancées dans
              <a
                :href="grafanaUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium underline hover:text-blue-800"
              >
                Grafana (hébergé séparément)
              </a>
            </p>
          </div>
        </div>
      </div>

      <!-- Wave 1 info -->
      <div class="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-gray-900 mb-2">Wave 1 (MVP) - État actuel</h3>
        <ul class="text-xs text-gray-600 space-y-1">
          <li>✅ Authentification JWT fonctionnelle</li>
          <li>✅ Affichage des runs actifs avec polling (10s)</li>
          <li>✅ Navigation vers la page Runs</li>
          <li>⏳ P&L avec données placeholder (Wave 3: endpoint /trades requis)</li>
          <li>⏳ Configuration, User Indicator, Optimizations, Trades, Logs (Wave 2-3)</li>
        </ul>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import BotStatus from '@/components/home/BotStatus.vue'
import PnLSummary from '@/components/home/PnLSummary.vue'

// Optional Grafana base URL from environment
const grafanaUrl = computed(() => import.meta.env.VITE_GRAFANA_BASE_URL)
</script>
