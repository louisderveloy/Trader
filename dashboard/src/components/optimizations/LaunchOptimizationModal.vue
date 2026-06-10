<template>
  <!-- Modal Backdrop -->
  <div class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4">
    <div class="bg-white rounded-lg shadow-lg max-w-lg w-full max-h-[90vh] overflow-y-auto">
      <div class="p-6">
        <h2 class="text-xl font-bold text-gray-900 mb-4">Lancer une optimisation</h2>

        <form @submit.prevent="handleSubmit" class="space-y-4">
          <!-- Study name -->
          <ConfigField
            id="study-name"
            label="Nom de l'étude"
            tooltip="Identifiant lisible de l'étude Optuna. Doit être unique et descriptif (ex: btc_2024_sharpe)."
            :model-value="form.study_name"
            type="text"
            @update:model-value="form.study_name = String($event)"
          />

          <!-- Symbol -->
          <div>
            <label for="opt-symbol" class="block text-sm font-medium text-gray-700 mb-1">
              Symbole
            </label>
            <select
              id="opt-symbol"
              v-model="form.symbol"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option v-for="s in symbols" :key="s" :value="s">{{ s }}</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">
              Paires disponibles (USDC uniquement ; l'USDT n'est pas autorisé dans l'UE)
            </p>
          </div>

          <!-- Timeframe -->
          <div>
            <label for="opt-timeframe" class="block text-sm font-medium text-gray-700 mb-1">
              Intervalle (timeframe)
            </label>
            <select
              id="opt-timeframe"
              v-model="form.timeframe"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option v-for="tf in TIMEFRAMES" :key="tf" :value="tf">{{ tf }}</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">Période des bougies analysées</p>
          </div>

          <!-- Objective -->
          <div>
            <label for="opt-objective" class="block text-sm font-medium text-gray-700 mb-1">
              Objectif d'optimisation
            </label>
            <select
              id="opt-objective"
              v-model="form.objective"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="sharpe_ratio">Sharpe Ratio</option>
              <option value="sortino_ratio">Sortino Ratio</option>
              <option value="profit_factor">Profit Factor</option>
              <option value="win_rate">Win Rate</option>
              <option value="total_return">Total Return</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">Métrique à maximiser pour évaluer les paramètres</p>
          </div>

          <!-- Trials & splits -->
          <ConfigField
            id="n-trials"
            label="Nombre d'essais"
            tooltip="Nombre d'essais Optuna par split de walk-forward. Plus d'essais = meilleurs résultats mais plus long."
            :model-value="form.n_trials"
            type="number"
            :min="1"
            :max="100000"
            :step="1"
            @update:model-value="form.n_trials = Number($event)"
          />
          <ConfigField
            id="n-splits"
            label="Splits walk-forward"
            tooltip="Nombre de fenêtres train/test glissantes. Plus de splits = validation plus robuste mais plus long."
            :model-value="form.n_splits"
            type="number"
            :min="1"
            :max="100"
            :step="1"
            @update:model-value="form.n_splits = Number($event)"
          />

          <!-- Multithread -->
          <label class="flex items-center gap-2 text-sm text-gray-700">
            <input v-model="form.multithread" type="checkbox" class="rounded border-gray-300" />
            Multithreading (utiliser tous les cœurs CPU)
          </label>

          <!-- Advanced (collapsible) -->
          <div class="border-t border-gray-200 pt-3">
            <button
              type="button"
              @click="showAdvanced = !showAdvanced"
              class="flex items-center gap-1 text-sm font-medium text-gray-700 hover:text-gray-900"
            >
              <span>{{ showAdvanced ? '▾' : '▸' }}</span> Avancé
            </button>

            <div v-if="showAdvanced" class="mt-3 space-y-4">
              <ConfigField
                id="opt-start-date"
                label="Date de début (optionnel)"
                tooltip="Première bougie incluse. Laisser vide pour utiliser toutes les données disponibles."
                :model-value="form.start_date"
                type="date"
                @update:model-value="form.start_date = String($event)"
              />
              <ConfigField
                id="opt-end-date"
                label="Date de fin (optionnel)"
                tooltip="Dernière bougie incluse. Doit être postérieure à la date de début."
                :model-value="form.end_date"
                type="date"
                @update:model-value="form.end_date = String($event)"
              />
              <ConfigField
                id="train-ratio"
                label="Ratio d'entraînement (optionnel)"
                tooltip="Proportion de chaque split utilisée pour l'entraînement (entre 0 et 1, ex: 0.75)."
                :model-value="form.train_ratio"
                type="number"
                :min="0.05"
                :max="0.95"
                :step="0.05"
                @update:model-value="form.train_ratio = $event === '' ? null : Number($event)"
              />
              <div>
                <label for="wf-mode" class="block text-sm font-medium text-gray-700 mb-1">
                  Mode walk-forward (optionnel)
                </label>
                <select
                  id="wf-mode"
                  v-model="form.walk_forward_mode"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option :value="null">Par défaut</option>
                  <option value="sliding">Sliding (fenêtre glissante)</option>
                  <option value="expanding">Expanding (fenêtre croissante)</option>
                </select>
              </div>
              <div>
                <label for="sampler" class="block text-sm font-medium text-gray-700 mb-1">
                  Sampler Optuna (optionnel)
                </label>
                <select
                  id="sampler"
                  v-model="form.sampler"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option :value="null">Par défaut</option>
                  <option value="tpe">TPE</option>
                  <option value="random">Random</option>
                  <option value="grid">Grid</option>
                  <option value="cmaes">CMA-ES</option>
                </select>
              </div>
              <div>
                <label for="pruner" class="block text-sm font-medium text-gray-700 mb-1">
                  Pruner Optuna (optionnel)
                </label>
                <select
                  id="pruner"
                  v-model="form.pruner"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option :value="null">Par défaut</option>
                  <option value="median">Median</option>
                  <option value="hyperband">Hyperband</option>
                  <option value="none">Aucun</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 pt-4">
            <button
              type="button"
              @click="$emit('close')"
              class="flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              :disabled="isLoading || !canSubmit"
              class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
            >
              {{ isLoading ? 'Lancement...' : 'Lancer' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import ConfigField from '@/components/common/ConfigField.vue'
import { getSymbols } from '@/api/runs'
import type { LaunchOptimizationRequest, OptimizationObjective } from '@/api/optimizations'

interface Props {
  isLoading?: boolean
}
withDefaults(defineProps<Props>(), { isLoading: false })

const emit = defineEmits<{
  close: []
  launch: [payload: LaunchOptimizationRequest]
}>()

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

const showAdvanced = ref(false)

// Selectable symbols come from the API (driven by AVAILABLE_SYMBOLS).
const symbols = ref<string[]>(['BTCUSDC'])

onMounted(async () => {
  try {
    const res = await getSymbols()
    if (res.symbols.length) {
      symbols.value = res.symbols
      form.symbol = res.default || res.symbols[0]
    }
  } catch {
    // Keep the safe default if the endpoint is unavailable.
  }
})

const form = reactive({
  study_name: '',
  symbol: 'BTCUSDC',
  timeframe: '15m',
  objective: 'sharpe_ratio' as OptimizationObjective,
  n_trials: 100,
  n_splits: 4,
  multithread: false,
  // Advanced
  start_date: '',
  end_date: '',
  train_ratio: null as number | null,
  walk_forward_mode: null as 'sliding' | 'expanding' | null,
  sampler: null as 'tpe' | 'random' | 'grid' | 'cmaes' | null,
  pruner: null as 'median' | 'hyperband' | 'none' | null,
})

const canSubmit = computed(() => {
  if (!form.study_name.trim() || !form.symbol || !form.timeframe) return false
  if (!Number.isInteger(form.n_trials) || form.n_trials < 1) return false
  if (!Number.isInteger(form.n_splits) || form.n_splits < 1) return false
  if (form.start_date && form.end_date && form.end_date <= form.start_date) return false
  return true
})

function handleSubmit() {
  if (!canSubmit.value) return

  const payload: LaunchOptimizationRequest = {
    study_name: form.study_name.trim(),
    symbol: form.symbol,
    timeframe: form.timeframe,
    objective: form.objective,
    n_trials: form.n_trials,
    n_splits: form.n_splits,
    multithread: form.multithread,
  }

  if (form.start_date) payload.start_date = form.start_date
  if (form.end_date) payload.end_date = form.end_date
  if (form.train_ratio !== null && !Number.isNaN(form.train_ratio)) {
    payload.train_ratio = form.train_ratio
  }
  if (form.walk_forward_mode) payload.walk_forward_mode = form.walk_forward_mode
  if (form.sampler) payload.sampler = form.sampler
  if (form.pruner) payload.pruner = form.pruner

  emit('launch', payload)
}
</script>
