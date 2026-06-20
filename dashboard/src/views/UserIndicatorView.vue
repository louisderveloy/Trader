<template>
  <AppLayout>
    <div class="max-w-3xl mx-auto">
      <!-- Page Header -->
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-gray-900">Indicateur Utilisateur</h1>
        <p class="mt-2 text-gray-600">
          Ajustez manuellement le signal [-1, 1] pour influencer les décisions du bot
        </p>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Error Alert -->
      <ErrorAlert v-if="error" :message="error" @dismiss="error = null" />

      <!-- Indicator Form -->
      <div v-else class="space-y-6">
        <div class="bg-white rounded-lg shadow p-6">
          <!-- Symbol Selection -->
          <div class="mb-6">
            <label for="symbol" class="block text-sm font-medium text-gray-700 mb-2">
              Symbole
            </label>
            <select
              v-model="selectedSymbol"
              id="symbol"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="BTCUSDC">BTC/USDC</option>
              <!-- More symbols can be added later for multi-pair support -->
            </select>
            <p class="mt-1 text-sm text-gray-500">
              Sélectionnez la paire de trading (BTC/USDC en v1)
            </p>
          </div>

          <!-- Signal Slider -->
          <div class="mb-6">
            <div class="flex items-center justify-between mb-2">
              <label for="signal-slider" class="block text-sm font-medium text-gray-700">
                Signal [-1 à 1]
              </label>
              <div class="relative group inline-block">
                <button
                  type="button"
                  class="w-5 h-5 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-xs font-bold hover:bg-blue-300 transition-colors"
                  @mouseenter="showSignalTooltip = true"
                  @mouseleave="showSignalTooltip = false"
                  @focus="showSignalTooltip = true"
                  @blur="showSignalTooltip = false"
                >
                  ?
                </button>
                <div
                  v-if="showSignalTooltip"
                  class="absolute bottom-full right-0 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg z-10 w-48"
                >
                  -1: Signal d'achat fort. 0: Neutre. +1: Signal de vente fort. Valeur positive = Baissier,
                  Valeur négative = Haussier.
                  <div class="absolute top-full right-4 border-4 border-transparent border-t-gray-900"></div>
                </div>
              </div>
            </div>

            <!-- Slider with visual feedback -->
            <div class="flex items-center gap-4">
              <input
                id="signal-slider"
                v-model.number="formData.signal"
                type="range"
                :min="-1"
                :max="1"
                :step="0.1"
                class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
              />
              <span class="text-2xl font-bold w-12 text-center" :class="getSignalColor(formData.signal)">
                {{ formData.signal.toFixed(1) }}
              </span>
            </div>

            <!-- Signal description -->
            <p class="mt-2 text-sm text-gray-600">
              {{ getSignalDescription(formData.signal) }}
            </p>

            <!-- Slider color indicator -->
            <div class="mt-4 flex justify-between text-xs text-gray-600">
              <span class="text-red-600">← Vente</span>
              <span>Neutre</span>
              <span class="text-green-600">Achat →</span>
            </div>
          </div>

          <!-- Note Field -->
          <div class="mb-6">
            <label for="note" class="block text-sm font-medium text-gray-700 mb-2">
              Note (optionnel)
            </label>
            <textarea
              v-model="formData.note"
              id="note"
              rows="3"
              placeholder="Ex: Signal technique fort, attendre confirmation..."
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            <p class="mt-1 text-sm text-gray-500">
              Ajoutez une note pour expliquer votre signal
            </p>
          </div>

          <!-- Expiration Duration -->
          <div class="mb-6">
            <label for="expires-in" class="block text-sm font-medium text-gray-700 mb-2">
              Valide pendant
            </label>
            <div class="relative group inline-block">
              <button
                type="button"
                class="w-5 h-5 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-xs font-bold hover:bg-blue-300 transition-colors ml-2"
                @mouseenter="showExpirationTooltip = true"
                @mouseleave="showExpirationTooltip = false"
                @focus="showExpirationTooltip = true"
                @blur="showExpirationTooltip = false"
              >
                ?
              </button>
              <div
                v-if="showExpirationTooltip"
                class="absolute bottom-full left-0 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg whitespace-nowrap z-10"
              >
                Durée de validité du signal. Après expiration, le signal est ignoré.
                <div class="absolute top-full left-4 border-4 border-transparent border-t-gray-900"></div>
              </div>
            </div>
            <select
              v-model.number="formData.expires_in_hours"
              id="expires-in"
              class="mt-2 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option :value="1">1 heure</option>
              <option :value="4">4 heures</option>
              <option :value="8">8 heures</option>
              <option :value="24">24 heures</option>
              <option :value="72">3 jours</option>
              <option :value="168">1 semaines</option>
              <option :value="336">2 semaines</option>
              <option :value="504">3 semaines</option>
              <option :value="720">1 mois</option>
              <option :value="2160">3 mois</option>
              <option :value="8760">1 ans</option>
            </select>
            <p class="mt-1 text-sm text-gray-500">
              Expire le: {{ getExpirationTime() }}
            </p>
          </div>

          <!-- Current Indicator Info (when ValueSet) -->
          <div v-if="userIndicator?.status === 'ValueSet'" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <h3 class="text-sm font-semibold text-blue-900 mb-2">Signal Actuel</h3>
            <p class="text-sm text-blue-800">
              Signal: <span class="font-bold" :class="getSignalColor(userIndicator.signal!)">{{
                userIndicator.signal!.toFixed(1)
              }}</span>
            </p>
            <p v-if="userIndicator.note" class="text-sm text-blue-800">
              Note: {{ userIndicator.note }}
            </p>
            <p class="text-sm text-blue-700">
              Expire: {{ formatDateTime(userIndicator.expires_at!) }}
            </p>
          </div>

          <!-- No Indicator Set Warning (when ValueNotSet) -->
          <div v-if="userIndicator?.status === 'ValueNotSet'" class="bg-red-50 border border-red-300 rounded-lg p-4 mb-6">
            <div class="flex items-start gap-3">
              <span class="text-2xl">⚠️</span>
              <div>
                <h3 class="text-sm font-semibold text-red-900 mb-1">Aucun signal actif</h3>
                <p class="text-sm text-red-800">Il n'y a pas de signal actif pour ce symbole.</p>
              </div>
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="flex gap-4 justify-end">
            <button
              @click="resetForm"
              class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Annuler
            </button>
            <button
              @click="saveIndicator"
              :disabled="isSaving"
              class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
            >
              {{ isSaving ? 'Enregistrement...' : 'Enregistrer' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import { formatDateTime } from '@/utils/format'

const configStore = useConfigStore()

const isLoading = computed(() => configStore.isLoading)
const userIndicator = computed(() => configStore.userIndicator)
const isSaving = ref(false)
const error = ref<string | null>(null)

const selectedSymbol = ref('BTCUSDC')
const showSignalTooltip = ref(false)
const showExpirationTooltip = ref(false)

// Form state
const formData = ref({
  signal: 0,
  note: '',
  expires_in_hours: 24
})

// Lifecycle
onMounted(async () => {
  await configStore.fetchUserIndicator(selectedSymbol.value)
  if (userIndicator.value && userIndicator.value.status === 'ValueSet' && userIndicator.value.signal !== null) {
    formData.value.signal = userIndicator.value.signal
    formData.value.note = userIndicator.value.note || ''
  }
})

// Helper functions
function getSignalColor(signal: number): string {
  if (signal < -0.5) return 'text-red-600'
  if (signal > 0.5) return 'text-green-600'
  return 'text-gray-600'
}

function getSignalDescription(signal: number): string {
  if (signal < -0.75) return 'Signal d\'achat très fort (très baissier)'
  if (signal < -0.5) return 'Signal d\'achat fort (baissier)'
  if (signal < -0.25) return 'Légèrement baissier'
  if (signal < 0.25) return 'Neutre'
  if (signal < 0.5) return 'Légèrement haussier'
  if (signal < 0.75) return 'Signal de vente fort (haussier)'
  return 'Signal de vente très fort (très haussier)'
}

function getExpirationTime(): string {
  const now = new Date()
  const expirationTime = new Date(now.getTime() + formData.value.expires_in_hours * 60 * 60 * 1000)
  return formatDateTime(expirationTime.toISOString())
}

function resetForm() {
  if (userIndicator.value) {
    formData.value.signal = userIndicator.value.signal
    formData.value.note = userIndicator.value.note || ''
    formData.value.expires_in_hours = 24
  } else {
    formData.value = {
      signal: 0,
      note: '',
      expires_in_hours: 24
    }
  }
}

async function saveIndicator() {
  isSaving.value = true
  error.value = null
  try {
    await configStore.updateIndicator(
      selectedSymbol.value,
      formData.value.signal,
      formData.value.note,
      formData.value.expires_in_hours
    )
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Erreur lors de l\'enregistrement'
  } finally {
    isSaving.value = false
  }
}
</script>

<style scoped>
/* Custom slider styling */
.slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
  cursor: pointer;
  border: none;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}
</style>
