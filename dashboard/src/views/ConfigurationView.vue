<template>
  <AppLayout>
    <div class="max-w-4xl mx-auto">
      <!-- Page Header -->
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-gray-900">Configuration</h1>
        <p class="mt-2 text-gray-600">Paramètres du bot de trading</p>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading" />

      <!-- Configuration Content -->
      <div v-else-if="config" class="space-y-8">
        <!-- Strategy Configuration -->
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-bold text-gray-900 mb-4">Stratégie</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
              id="entry_threshold"
              label="Seuil d'entrée"
              tooltip="Score pondéré minimum pour déclencher une entrée. Plage: -1 à 1. Valeurs plus élevées = signaux plus rares et plus forts."
              :model-value="formData.strategy.entry_threshold"
              type="number"
              :min="-1"
              :max="1"
              :step="0.1"
              @update:model-value="updateStrategyField('entry_threshold', $event)"
            />
            <ConfigField
              id="exit_threshold"
              label="Seuil de sortie"
              tooltip="Score pondéré pour déclencher une sortie. Plage: -1 à 1. Négatif = attendre inversion du signal."
              :model-value="formData.strategy.exit_threshold"
              type="number"
              :min="-1"
              :max="1"
              :step="0.1"
              @update:model-value="updateStrategyField('exit_threshold', $event)"
            />
            <ConfigField
              id="confirmation_candles"
              label="Bougies de confirmation"
              tooltip="Nombre de bougies pour confirmer un signal avant d'agir. Prévient le repainting. Plus élevé = plus conservateur."
              :model-value="formData.strategy.confirmation_candles"
              type="number"
              :min="1"
              :max="10"
              @update:model-value="updateStrategyField('confirmation_candles', $event)"
            />
          </div>
        </div>

        <!-- Risk Management Configuration -->
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-bold text-gray-900 mb-4">Gestion des Risques</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
              id="max_trades_per_day"
              label="Max trades par jour"
              tooltip="Nombre maximum de transactions (ordres) par jour. Limites l'exposition et la surexécution."
              :model-value="formData.risk.max_trades_per_day"
              type="number"
              :min="1"
              :max="50"
              @update:model-value="updateRiskField('max_trades_per_day', $event)"
            />
            <ConfigField
              id="max_exposure_percent"
              label="Max exposition (%)"
              tooltip="Pourcentage maximum du capital pouvant être exposé simultanément. 30% = 30% du solde utilisé pour les positions."
              :model-value="formData.risk.max_exposure_percent"
              type="number"
              :min="5"
              :max="100"
              :step="5"
              @update:model-value="updateRiskField('max_exposure_percent', $event)"
            />
            <ConfigField
              id="position_size_mode"
              label="Mode de dimensionnement"
              tooltip="Fixe: taille identique à chaque trade. Confiance: proportionnel au score. ATR: selon la volatilité."
              :model-value="formData.risk.position_size_mode"
              type="text"
              disabled
              help-text="Éditable via API uniquement"
            />
            <ConfigField
              id="fixed_size_usdt"
              label="Taille fixe (USDT)"
              tooltip="Montant en USDT pour chaque trade en mode Fixe. Ignoré en mode Confiance ou ATR."
              :model-value="formData.risk.fixed_size_usdt"
              type="number"
              :min="10"
              :max="10000"
              :step="10"
              @update:model-value="updateRiskField('fixed_size_usdt', $event)"
            />
            <ConfigField
              id="atr_multiplier"
              label="Multiplicateur ATR"
              tooltip="Facteur appliqué à l'ATR pour dimensionner la position en mode ATR. Plus élevé = positions plus grandes."
              :model-value="formData.risk.atr_multiplier"
              type="number"
              :min="0.5"
              :max="5"
              :step="0.5"
              @update:model-value="updateRiskField('atr_multiplier', $event)"
            />
            <ConfigField
              id="capital_risk_percent"
              label="% capital à risquer"
              tooltip="Pourcentage du capital à risquer par trade en mode ATR. 1% = stop-loss place pour risquer 1% du solde."
              :model-value="formData.risk.capital_risk_percent"
              type="number"
              :min="0.1"
              :max="5"
              :step="0.1"
              @update:model-value="updateRiskField('capital_risk_percent', $event)"
            />
          </div>
        </div>

        <!-- Stop-Loss & Take-Profit Configuration -->
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-bold text-gray-900 mb-4">Stop-Loss & Take-Profit</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
              id="sl_mode"
              label="Mode Stop-Loss"
              tooltip="ATR: Stop-loss basé sur la volatilité (ATR). Fixe: pourcentage fixe du prix d'entrée."
              :model-value="formData.stopLossTakeProfit.sl_mode"
              type="text"
              disabled
              help-text="Éditable via API uniquement"
            />
            <ConfigField
              id="sl_atr_multiplier"
              label="Multiplicateur SL ATR"
              tooltip="Facteur ATR pour placer le stop-loss. 2.0 = SL à 2× l'ATR sous l'entrée."
              :model-value="formData.stopLossTakeProfit.sl_atr_multiplier"
              type="number"
              :min="0.5"
              :max="5"
              :step="0.5"
              @update:model-value="updateSLTPField('sl_atr_multiplier', $event)"
            />
            <ConfigField
              id="sl_fixed_percent"
              label="SL fixe (%)"
              tooltip="Pourcentage fixe sous le prix d'entrée (mode SL Fixe). 2% = stop à 2% sous l'entrée."
              :model-value="formData.stopLossTakeProfit.sl_fixed_percent"
              type="number"
              :min="0.5"
              :max="10"
              :step="0.5"
              @update:model-value="updateSLTPField('sl_fixed_percent', $event)"
            />
            <ConfigField
              id="tp_mode"
              label="Mode Take-Profit"
              tooltip="ATR: TP basé sur la volatilité (ATR). Fixe: pourcentage fixe du prix d'entrée."
              :model-value="formData.stopLossTakeProfit.tp_mode"
              type="text"
              disabled
              help-text="Éditable via API uniquement"
            />
            <ConfigField
              id="tp_atr_multiplier"
              label="Multiplicateur TP ATR"
              tooltip="Facteur ATR pour placer le take-profit. 3.0 = TP à 3× l'ATR au-dessus de l'entrée."
              :model-value="formData.stopLossTakeProfit.tp_atr_multiplier"
              type="number"
              :min="0.5"
              :max="5"
              :step="0.5"
              @update:model-value="updateSLTPField('tp_atr_multiplier', $event)"
            />
            <ConfigField
              id="tp_fixed_percent"
              label="TP fixe (%)"
              tooltip="Pourcentage fixe au-dessus du prix d'entrée (mode TP Fixe). 4% = TP à 4% au-dessus de l'entrée."
              :model-value="formData.stopLossTakeProfit.tp_fixed_percent"
              type="number"
              :min="0.5"
              :max="20"
              :step="0.5"
              @update:model-value="updateSLTPField('tp_fixed_percent', $event)"
            />
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
            @click="saveConfiguration"
            :disabled="isSaving"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
          >
            {{ isSaving ? 'Enregistrement...' : 'Enregistrer' }}
          </button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useToastStore } from '@/stores/toast'
import AppLayout from '@/components/layout/AppLayout.vue'
import ConfigField from '@/components/common/ConfigField.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const configStore = useConfigStore()
const toastStore = useToastStore()

const isLoading = computed(() => configStore.isLoading)
const config = computed(() => configStore.config)
const isSaving = ref(false)

// Form state
const formData = ref({
  strategy: {
    entry_threshold: 0.6,
    exit_threshold: -0.3,
    confirmation_candles: 2
  },
  risk: {
    max_trades_per_day: 5,
    max_exposure_percent: 30,
    position_size_mode: 'confidence',
    fixed_size_usdt: 100,
    atr_multiplier: 2,
    capital_risk_percent: 1
  },
  stopLossTakeProfit: {
    sl_mode: 'atr',
    sl_atr_multiplier: 2,
    sl_fixed_percent: 2,
    tp_mode: 'atr',
    tp_atr_multiplier: 3,
    tp_fixed_percent: 4
  }
})

// Lifecycle
onMounted(async () => {
  await configStore.fetchConfig()
  if (configStore.config) {
    formData.value.strategy = { ...configStore.config.strategy }
    formData.value.risk = { ...configStore.config.risk }
    formData.value.stopLossTakeProfit = { ...configStore.config.stop_loss_take_profit }
  }
})

// Form methods
function updateStrategyField(field: string, value: unknown) {
  formData.value.strategy = {
    ...formData.value.strategy,
    [field]: value
  }
}

function updateRiskField(field: string, value: unknown) {
  formData.value.risk = {
    ...formData.value.risk,
    [field]: value
  }
}

function updateSLTPField(field: string, value: unknown) {
  formData.value.stopLossTakeProfit = {
    ...formData.value.stopLossTakeProfit,
    [field]: value
  }
}

function resetForm() {
  if (configStore.config) {
    formData.value.strategy = { ...configStore.config.strategy }
    formData.value.risk = { ...configStore.config.risk }
    formData.value.stopLossTakeProfit = { ...configStore.config.stop_loss_take_profit }
  }
}

async function saveConfiguration() {
  isSaving.value = true
  try {
    await configStore.updateStrategy(formData.value.strategy)
    await configStore.updateRisk(formData.value.risk)
    // Note: stop-loss/take-profit update would require API endpoint
    // For now, just update strategy and risk

    // Show success toast
    toastStore.success('Configuration enregistrée avec succès')
  } catch (err) {
    // Show error toast
    const errorMessage = err instanceof Error ? err.message : 'Erreur lors de l\'enregistrement'
    toastStore.error(errorMessage)
  } finally {
    isSaving.value = false
  }
}
</script>
