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
                tooltip="Fixe : un pourcentage fixe du capital total à chaque transaction. Confiance : la taille est proportionnelle à la force du signal calculé. Indicateur de volatilité (moyenne de l'amplitude de prix sur plusieurs bougies) : la taille est calculée à partir du niveau de volatilité récent du marché et du pourcentage de capital que vous acceptez de risquer."
                :model-value="formData.risk.position_size_mode"
                :options="positionSizeModeOptions"
                @update:model-value="updateRiskField('position_size_mode', $event)"
            />
            <ConfigField
                id="fixed_size_percent"
                label="Taille fixe (% du capital)"
                tooltip="Pourcentage du capital total investi à chaque transaction lorsque le mode de dimensionnement Fixe est sélectionné. Par exemple, 10% signifie que chaque position utilise 10% du solde disponible. Ce paramètre est ignoré dans les modes Confiance ou Indicateur de volatilité."
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
                tooltip="Facteur multiplicateur appliqué à l'indicateur de volatilité (moyenne de l'amplitude de prix récente) pour calculer la taille de la position lorsque le mode de dimensionnement par volatilité est sélectionné. Plus ce facteur est élevé, plus les positions ouvertes seront grandes."
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
                tooltip="Pourcentage du capital total que vous acceptez de perdre sur une seule transaction lorsque le mode de dimensionnement par volatilité est sélectionné. Par exemple, 1% signifie que le seuil de protection (stop-loss) est positionné de façon à ce qu'au maximum 1% du solde soit perdu si ce seuil est atteint."
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
          <p class="text-sm text-gray-600 mb-6 leading-relaxed">
            Le seuil de protection (stop-loss) ferme automatiquement une position perdante pour limiter la perte,
            et le seuil de prise de bénéfice (take-profit) ferme automatiquement une position gagnante pour
            sécuriser le gain. Deux façons de calculer ces deux seuils sont disponibles :
            un <strong>pourcentage fixe</strong> ou un calcul basé sur la <strong>volatilité du marché</strong>.
            Un pourcentage fixe place toujours le seuil à la même distance du prix d'entrée (par exemple 2% en
            dessous pour la protection), quelles que soient les conditions de marché : simple et prévisible, mais
            ce seuil peut être trop serré pendant une période agitée (déclenchement prématuré) ou trop large
            pendant une période calme (perte plus importante que nécessaire avant la fermeture). Le calcul basé
            sur la volatilité du marché utilise un indicateur qui mesure l'amplitude moyenne des mouvements de
            prix sur les dernières bougies (plus cette amplitude est grande, plus le marché bouge fort) :
            le seuil est alors placé à une distance proportionnelle à cette amplitude récente, multipliée par
            le facteur choisi ci-dessous. Concrètement, ce calcul adapte automatiquement la distance du seuil aux
            conditions réelles du marché : il s'éloigne du prix d'entrée quand le marché est agité (pour éviter
            une fermeture prématurée sur du simple bruit) et se rapproche quand le marché est calme (pour ne pas
            laisser une perte ou un gain non protégé s'accumuler inutilement).
          </p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConfigField
                id="sl_mode"
                label="Mode Stop-Loss"
                tooltip="Détermine comment est calculée la distance du seuil de protection par rapport au prix d'entrée. Indicateur de volatilité : seuil basé sur l'amplitude moyenne récente des mouvements de prix. Fixe : pourcentage fixe du prix d'entrée, identique quelles que soient les conditions de marché."
                :model-value="formData.stopLossTakeProfit.sl_mode"
                :options="stopLossTakeProfitModeOptions"
                @update:model-value="updateSLTPField('sl_mode', $event)"
            />
            <ConfigField
                id="sl_atr_multiplier"
                label="Multiplicateur SL Indicateur de volatilité"
                tooltip="Facteur multiplicateur appliqué à l'indicateur de volatilité pour positionner le seuil de protection lorsque le mode basé sur la volatilité est sélectionné. Par exemple, une valeur de 2,0 place le seuil de protection à une distance égale à deux fois l'amplitude moyenne récente des mouvements de prix, en dessous du prix d'entrée."
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
                tooltip="Pourcentage fixe en dessous du prix d'entrée auquel le seuil de protection est placé lorsque le mode fixe est sélectionné. Par exemple, 2% signifie que la position se ferme automatiquement si le prix descend à 2% sous le prix d'entrée."
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
                tooltip="Détermine comment est calculée la distance du seuil de prise de bénéfice par rapport au prix d'entrée. Indicateur de volatilité : seuil basé sur l'amplitude moyenne récente des mouvements de prix. Fixe : pourcentage fixe du prix d'entrée, identique quelles que soient les conditions de marché."
                :model-value="formData.stopLossTakeProfit.tp_mode"
                :options="stopLossTakeProfitModeOptions"
                @update:model-value="updateSLTPField('tp_mode', $event)"
            />
            <ConfigField
                id="tp_atr_multiplier"
                label="Multiplicateur TP Indicateur de volatilité"
                tooltip="Facteur multiplicateur appliqué à l'indicateur de volatilité pour positionner le seuil de prise de bénéfice lorsque le mode basé sur la volatilité est sélectionné. Par exemple, une valeur de 3,0 place le seuil de prise de bénéfice à une distance égale à trois fois l'amplitude moyenne récente des mouvements de prix, au-dessus du prix d'entrée."
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
                tooltip="Pourcentage fixe au-dessus du prix d'entrée auquel le seuil de prise de bénéfice est placé lorsque le mode fixe est sélectionné. Par exemple, 4% signifie que la position se ferme automatiquement si le prix monte à 4% au-dessus du prix d'entrée."
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
  }
})

// Lifecycle
onMounted(async () => {
  await configStore.fetchConfig()
  if (configStore.config) {
    formData.value.strategy = {...configStore.config.strategy}
    formData.value.risk = {...configStore.config.risk}
    formData.value.stopLossTakeProfit = {...configStore.config.stop_loss_take_profit}
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
    formData.value.strategy = {...configStore.config.strategy}
    formData.value.risk = {...configStore.config.risk}
    formData.value.stopLossTakeProfit = {...configStore.config.stop_loss_take_profit}
  }
}

async function saveConfiguration() {
  isSaving.value = true
  try {
    // Validate that entry_threshold > exit_threshold
    if (formData.value.strategy.entry_threshold <= formData.value.strategy.exit_threshold) {
      toastStore.error(
          `Le seuil d'entrée (${formData.value.strategy.entry_threshold}) doit être supérieur au seuil de sortie (${formData.value.strategy.exit_threshold})`
      )
      isSaving.value = false
      return
    }

    await configStore.updateStrategy(formData.value.strategy)
    await configStore.updateRisk(formData.value.risk)
    await configStore.updateStopLossTakeProfit(formData.value.stopLossTakeProfit)

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
