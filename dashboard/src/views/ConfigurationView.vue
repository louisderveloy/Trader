<template>
  <AppLayout>
    <div class="max-w-4xl mx-auto">
      <!-- Page Header -->
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-gray-900">Configuration</h1>
        <p class="mt-2 text-gray-600">Paramètres du bot de trading</p>
      </div>

      <!-- Loading State -->
      <LoadingSpinner v-if="isLoading"/>

      <!-- Configuration Content -->
      <div v-else-if="config" class="space-y-8">
        <!-- Trading Engine Selection -->
        <div class="bg-white rounded-lg shadow p-6">
          <div class="mb-4">
            <h2 class="text-xl font-bold text-gray-900">Moteur de Trading</h2>
            <p class="text-sm text-gray-600 mt-1">Choisissez le moteur décisionnel utilisé pour exécuter la stratégie</p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- Scoring Multi-Indicateurs -->
            <div
                @click="setTradingEngine('indicators')"
                class="relative flex flex-col p-4 border rounded-lg cursor-pointer transition-all"
                :class="formData.trading_engine.engine_type === 'indicators' ? 'border-blue-600 bg-blue-50/40 ring-2 ring-blue-500' : 'border-gray-200 bg-white hover:border-gray-300'"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="font-semibold text-gray-900">Scoring Multi-Indicateurs</span>
                <input
                    type="radio"
                    name="engine_type"
                    value="indicators"
                    :checked="formData.trading_engine.engine_type === 'indicators'"
                    class="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                />
              </div>
              <p class="text-xs text-gray-600 leading-relaxed">
                Moteur algorithmique classique combinant plusieurs indicateurs techniques (EMA, MACD, RSI, etc.) pondérés selon les résultats d'optimisation Optuna.
              </p>
            </div>

            <!-- Modèle Prédictif -->
            <div
                @click="setTradingEngine('predictive_model')"
                class="relative flex flex-col p-4 border rounded-lg cursor-pointer transition-all"
                :class="formData.trading_engine.engine_type === 'predictive_model' ? 'border-blue-600 bg-blue-50/40 ring-2 ring-blue-500' : 'border-gray-200 bg-white hover:border-gray-300'"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="font-semibold text-gray-900">Modèle Prédictif</span>
                <input
                    type="radio"
                    name="engine_type"
                    value="predictive_model"
                    :checked="formData.trading_engine.engine_type === 'predictive_model'"
                    class="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                />
              </div>
              <p class="text-xs text-gray-600 leading-relaxed">
                Moteur autonome basé sur un modèle prédictif évaluant directement les probabilités de hausse, baisse ou maintien à partir des séquences de marché récentes.
              </p>
            </div>
          </div>
        </div>

        <!-- Strategy Configuration -->
        <div class="bg-white rounded-lg shadow p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-bold text-gray-900">Stratégie</h2>
            <span v-if="isPredictive" class="text-xs font-medium px-2.5 py-1 bg-purple-100 text-purple-800 rounded-full">
              Mode Modèle Prédictif (Probabilités)
            </span>
            <span v-else class="text-xs font-medium px-2.5 py-1 bg-blue-100 text-blue-800 rounded-full">
              Mode Multi-Indicateurs (Score)
            </span>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
                v-if="!isPredictive"
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
                v-else
                id="entry_threshold_pred"
                label="Seuil d'entrée (Probabilité Achat)"
                tooltip="Probabilité minimale calculée par le modèle prédictif pour déclencher un achat. Plage: 0.0 à 1.0 (ex: 0.845 = 84.5%)."
                :model-value="formData.strategy.entry_threshold"
                type="number"
                :min="0"
                :max="1"
                :step="0.005"
                @update:model-value="updateStrategyField('entry_threshold', $event)"
            />

            <ConfigField
                v-if="!isPredictive"
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
                v-else
                id="exit_threshold_pred"
                label="Seuil de sortie (Probabilité Vente)"
                tooltip="Probabilité minimale calculée par le modèle prédictif pour déclencher la fermeture de position. Plage: 0.0 à 1.0 (ex: 0.880 = 88.0%)."
                :model-value="formData.strategy.exit_threshold"
                type="number"
                :min="0"
                :max="1"
                :step="0.005"
                @update:model-value="updateStrategyField('exit_threshold', $event)"
            />

            <ConfigField
                v-if="!isPredictive"
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
                tooltip="Nombre maximum de transactions (ordres) par jour. Limite l'exposition et la surexécution."
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
                tooltip="Fixe : un pourcentage fixe du capital total à chaque transaction. Confiance : la taille est proportionnelle à la force du signal calculé. Indicateur de volatilité : la taille est calculée à partir du niveau de volatilité récent du marché et du pourcentage de capital que vous acceptez de risquer."
                :model-value="formData.risk.position_size_mode"
                :options="positionSizeModeOptions"
                @update:model-value="updateRiskField('position_size_mode', $event)"
            />
            <ConfigField
                id="fixed_size_percent"
                label="Taille fixe (% du capital)"
                tooltip="Pourcentage du capital total investi à chaque transaction lorsque le mode de dimensionnement Fixe est sélectionné. Par exemple, 10% signifie que chaque position utilise 10% du solde disponible."
                :model-value="formData.risk.fixed_size_percent"
                type="number"
                :min="1"
                :max="100"
                :step="1"
                @update:model-value="updateRiskField('fixed_size_percent', $event)"
            />
            <ConfigField
                id="atr_multiplier"
                label="Multiplicateur de volatilité"
                tooltip="Facteur multiplicateur appliqué à l'indicateur de volatilité pour calculer la taille de la position lorsque le mode de dimensionnement par volatilité est sélectionné."
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
                tooltip="Pourcentage du capital total que vous acceptez de perdre sur une seule transaction lorsque le mode de dimensionnement par volatilité est sélectionné."
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
          <div v-if="isPredictive" class="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900 leading-relaxed">
            ℹ️ <strong>Mode Fixe actif :</strong> Pour le Modèle Prédictif, le Stop-Loss et le Take-Profit sont toujours calculés en pourcentage fixe du prix d'entrée lors de l'ouverture de position.
          </div>
          <p v-else class="text-sm text-gray-600 mb-6 leading-relaxed">
            Le seuil de protection (stop-loss) ferme automatiquement une position perdante pour limiter la perte,
            et le seuil de prise de bénéfice (take-profit) ferme automatiquement une position gagnante pour
            sécuriser le gain. Deux façons de calculer ces deux seuils sont disponibles :
            un <strong>pourcentage fixe</strong> ou un calcul basé sur la <strong>volatilité du marché</strong>.
          </p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
                v-if="!isPredictive"
                id="sl_mode"
                label="Mode Stop-Loss"
                tooltip="Détermine comment est calculée la distance du seuil de protection par rapport au prix d'entrée. Indicateur de volatilité : seuil basé sur l'amplitude moyenne récente des mouvements de prix. Fixe : pourcentage fixe du prix d'entrée, identique quelles que soient les conditions de marché."
                :model-value="formData.stopLossTakeProfit.sl_mode"
                :options="stopLossTakeProfitModeOptions"
                @update:model-value="updateSLTPField('sl_mode', $event)"
            />
            <ConfigField
                v-if="!isPredictive && formData.stopLossTakeProfit.sl_mode === 'atr'"
                id="sl_atr_multiplier"
                label="Multiplicateur SL Indicateur de volatilité"
                tooltip="Facteur multiplicateur appliqué à l'indicateur de volatilité pour positionner le seuil de protection lorsque le mode basé sur la volatilité est sélectionné."
                :model-value="formData.stopLossTakeProfit.sl_atr_multiplier"
                type="number"
                :min="0.5"
                :max="5"
                :step="0.5"
                @update:model-value="updateSLTPField('sl_atr_multiplier', $event)"
            />
            <ConfigField
                v-if="isPredictive || formData.stopLossTakeProfit.sl_mode === 'fixed'"
                id="sl_fixed_percent"
                label="SL fixe (%)"
                tooltip="Pourcentage fixe en dessous du prix d'entrée auquel le seuil de protection est placé. Par exemple, 7.9% signifie que la position se ferme automatiquement si le prix descend de 7.9% sous le prix d'entrée."
                :model-value="formData.stopLossTakeProfit.sl_fixed_percent"
                type="number"
                :min="0.1"
                :max="20"
                :step="0.1"
                @update:model-value="updateSLTPField('sl_fixed_percent', $event)"
            />
            <ConfigField
                v-if="!isPredictive"
                id="tp_mode"
                label="Mode Take-Profit"
                tooltip="Détermine comment est calculée la distance du seuil de prise de bénéfice par rapport au prix d'entrée. Indicateur de volatilité : seuil basé sur l'amplitude moyenne récente des mouvements de prix. Fixe : pourcentage fixe du prix d'entrée, identique quelles que soient les conditions de marché."
                :model-value="formData.stopLossTakeProfit.tp_mode"
                :options="stopLossTakeProfitModeOptions"
                @update:model-value="updateSLTPField('tp_mode', $event)"
            />
            <ConfigField
                v-if="!isPredictive && formData.stopLossTakeProfit.tp_mode === 'atr'"
                id="tp_atr_multiplier"
                label="Multiplicateur TP Indicateur de volatilité"
                tooltip="Facteur multiplicateur appliqué à l'indicateur de volatilité pour positionner le seuil de prise de bénéfice lorsque le mode basé sur la volatilité est sélectionné."
                :model-value="formData.stopLossTakeProfit.tp_atr_multiplier"
                type="number"
                :min="0.5"
                :max="5"
                :step="0.5"
                @update:model-value="updateSLTPField('tp_atr_multiplier', $event)"
            />
            <ConfigField
                v-if="isPredictive || formData.stopLossTakeProfit.tp_mode === 'fixed'"
                id="tp_fixed_percent"
                label="TP fixe (%)"
                tooltip="Pourcentage fixe au-dessus du prix d'entrée auquel le seuil de prise de bénéfice est placé. Par exemple, 1.1% signifie que la position se ferme automatiquement si le prix monte de 1.1% au-dessus du prix d'entrée."
                :model-value="formData.stopLossTakeProfit.tp_fixed_percent"
                type="number"
                :min="0.1"
                :max="20"
                :step="0.1"
                @update:model-value="updateSLTPField('tp_fixed_percent', $event)"
            />
          </div>
        </div>

        <!-- Cooldown Configuration -->
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-bold text-gray-900 mb-4">Cooldown</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
                id="cooldown_after_trade_seconds"
                label="Cooldown après trade (secondes)"
                tooltip="Délai d'attente, en secondes, après la fermeture d'un trade avant que le bot puisse en ouvrir un nouveau. Empêche les ré-entrées trop rapides. Exemple : 3600 = 1 heure. 0 = aucun cooldown. Plage : 0 à 86400 (24h)."
                :model-value="formData.cooldown.after_trade_seconds"
                type="number"
                :min="0"
                :max="86400"
                :step="60"
                @update:model-value="updateCooldownField('after_trade_seconds', $event)"
            />
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="flex gap-4 justify-end">
          <button
              @click="resetForm"
              class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Réinitialiser
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
import {computed, onMounted, ref} from 'vue'
import {useConfigStore} from '@/stores/config'
import {useToastStore} from '@/stores/toast'
import AppLayout from '@/components/layout/AppLayout.vue'
import ConfigField from '@/components/common/ConfigField.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'

const configStore = useConfigStore()
const toastStore = useToastStore()

const isLoading = computed(() => configStore.isLoading)
const config = computed(() => configStore.config)
const isSaving = ref(false)

const stopLossTakeProfitModeOptions = [
  {value: 'atr', label: 'Indicateur de volatilité'},
  {value: 'fixed', label: 'Fixe'}
]

const positionSizeModeOptions = [
  {value: 'fixed', label: 'Fixe'},
  {value: 'confidence', label: 'Confiance'},
  {value: 'risk_atr', label: 'Indicateur de volatilité'}
]

// Form state
const formData = ref({
  trading_engine: {
    engine_type: 'indicators' as 'indicators' | 'predictive_model'
  },
  strategy: {
    entry_threshold: 0.6,
    exit_threshold: -0.3,
    confirmation_candles: 2
  },
  risk: {
    max_trades_per_day: 5,
    max_exposure_percent: 30,
    position_size_mode: 'confidence',
    fixed_size_percent: 10,
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
  },
  cooldown: {
    after_trade_seconds: 3600
  }
})

const isPredictive = computed(() => formData.value.trading_engine.engine_type === 'predictive_model')

function setTradingEngine(type: 'indicators' | 'predictive_model') {
  formData.value.trading_engine.engine_type = type
  if (type === 'predictive_model') {
    // Default recommended fixed SL/TP for predictive model
    formData.value.stopLossTakeProfit.sl_mode = 'fixed'
    formData.value.stopLossTakeProfit.tp_mode = 'fixed'
    if (formData.value.strategy.entry_threshold < 0) {
      formData.value.strategy.entry_threshold = 0.845
    }
    if (formData.value.strategy.exit_threshold < 0) {
      formData.value.strategy.exit_threshold = 0.880
    }
  } else {
    if (formData.value.strategy.entry_threshold > 1) {
      formData.value.strategy.entry_threshold = 0.6
    }
    if (formData.value.strategy.exit_threshold > 0) {
      formData.value.strategy.exit_threshold = -0.3
    }
  }
}

// Lifecycle
onMounted(async () => {
  await configStore.fetchConfig()
  if (configStore.config) {
    if (configStore.config.trading_engine) {
      formData.value.trading_engine = {...configStore.config.trading_engine}
    }
    formData.value.strategy = {...configStore.config.strategy}
    formData.value.risk = {...configStore.config.risk}
    formData.value.stopLossTakeProfit = {...configStore.config.stop_loss_take_profit}
    formData.value.cooldown = {...configStore.config.cooldown}
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

function updateCooldownField(field: string, value: unknown) {
  formData.value.cooldown = {
    ...formData.value.cooldown,
    [field]: value
  }
}

function resetForm() {
  if (configStore.config) {
    if (configStore.config.trading_engine) {
      formData.value.trading_engine = {...configStore.config.trading_engine}
    }
    formData.value.strategy = {...configStore.config.strategy}
    formData.value.risk = {...configStore.config.risk}
    formData.value.stopLossTakeProfit = {...configStore.config.stop_loss_take_profit}
    formData.value.cooldown = {...configStore.config.cooldown}
  }
}

async function saveConfiguration() {
  isSaving.value = true
  try {
    if (formData.value.trading_engine.engine_type === 'indicators') {
      // Validate that entry_threshold > exit_threshold
      if (formData.value.strategy.entry_threshold <= formData.value.strategy.exit_threshold) {
        toastStore.error(
            `Le seuil d'entrée (${formData.value.strategy.entry_threshold}) doit être supérieur au seuil de sortie (${formData.value.strategy.exit_threshold})`
        )
        isSaving.value = false
        return
      }
    } else {
      // Validate probabilities in [0, 1]
      if (formData.value.strategy.entry_threshold < 0 || formData.value.strategy.entry_threshold > 1) {
        toastStore.error("Le seuil de probabilité d'achat doit être compris entre 0.0 et 1.0")
        isSaving.value = false
        return
      }
      if (formData.value.strategy.exit_threshold < 0 || formData.value.strategy.exit_threshold > 1) {
        toastStore.error("Le seuil de probabilité de vente doit être compris entre 0.0 et 1.0")
        isSaving.value = false
        return
      }
      // Force fixed mode
      formData.value.stopLossTakeProfit.sl_mode = 'fixed'
      formData.value.stopLossTakeProfit.tp_mode = 'fixed'
    }

    await configStore.updateTradingEngine(formData.value.trading_engine)
    await configStore.updateStrategy(formData.value.strategy)
    await configStore.updateRisk(formData.value.risk)
    await configStore.updateStopLossTakeProfit(formData.value.stopLossTakeProfit)
    await configStore.updateCooldown(formData.value.cooldown)

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
