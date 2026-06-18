<template>
  <!-- Modal Backdrop -->
  <div class="fixed inset-0 z-50 bg-black bg-opacity-50 flex sm:items-center sm:justify-center sm:p-4">
    <div class="bg-white w-full h-full overflow-y-auto overscroll-contain sm:h-auto sm:max-w-lg sm:max-h-[90vh] sm:rounded-lg sm:shadow-lg">
      <div class="p-6">
        <h2 class="text-xl font-bold text-gray-900 mb-4">Démarrer un run</h2>

        <form @submit.prevent="handleSubmit" class="space-y-4">
          <!-- Run type selector -->
          <div>
            <label for="run-type" class="block text-sm font-medium text-gray-700 mb-1">
              Type de run
            </label>
            <select
              id="run-type"
              v-model="form.run_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="backtest">Backtest</option>
              <option value="paper">Paper Trading</option>
              <option value="live">Live</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">{{ runTypeHelp }}</p>
          </div>

          <!-- Shared: symbol + timeframe -->
          <div>
            <label for="symbol" class="block text-sm font-medium text-gray-700 mb-1">
              Symbole
            </label>
            <select
              id="symbol"
              v-model="form.symbol"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option v-for="s in symbols" :key="s" :value="s">{{ s }}</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">
              Paires disponibles (USDC uniquement ; l'USDT n'est pas autorisé dans l'UE)
            </p>
          </div>

          <div>
            <label for="timeframe" class="block text-sm font-medium text-gray-700 mb-1">
              Intervalle (timeframe)
            </label>
            <select
              id="timeframe"
              v-model="form.timeframe"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option v-for="tf in TIMEFRAMES" :key="tf" :value="tf">{{ tf }}</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">Période des bougies analysées</p>
          </div>

          <!-- Backtest-specific -->
          <template v-if="form.run_type === 'backtest'">
            <ConfigField
              id="start-date"
              label="Date de début"
              tooltip="Première bougie incluse dans le backtest (date ISO)."
              :model-value="form.start_date"
              type="date"
              @update:model-value="form.start_date = String($event)"
            />
            <ConfigField
              id="end-date"
              label="Date de fin"
              tooltip="Dernière bougie incluse. Doit être postérieure à la date de début."
              :model-value="form.end_date"
              type="date"
              @update:model-value="form.end_date = String($event)"
            />
            <ConfigField
              id="initial-capital"
              label="Capital initial (USDC)"
              tooltip="Capital de départ simulé pour le backtest. Entier positif (0 < x < 2 147 483 647)."
              :model-value="form.initial_capital"
              type="number"
              :min="1"
              :max="2147483646"
              :step="1"
              @update:model-value="form.initial_capital = Number($event)"
            />
            <div>
              <label for="engine" class="block text-sm font-medium text-gray-700 mb-1">
                Moteur de backtest
              </label>
              <select
                id="engine"
                v-model="form.engine"
                class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="vectorbt">vectorbt (rapide, vectorisé)</option>
                <option value="event_driven">event_driven (réaliste)</option>
              </select>
              <p class="mt-1 text-xs text-gray-500">
                vectorbt pour la vitesse, event_driven pour simuler le live exactement
              </p>
            </div>
            <ConfigField
              id="weights-set-id"
              label="Set de poids (UUID, optionnel)"
              tooltip="UUID d'un set de poids spécifique. Laisser vide pour utiliser le set actif."
              :model-value="form.weights_set_id"
              type="text"
              @update:model-value="form.weights_set_id = String($event)"
            />
          </template>

          <!-- Paper-specific -->
          <template v-if="form.run_type === 'paper'">
            <ConfigField
              id="paper-initial-capital"
              label="Capital initial (USDC)"
              tooltip="Capital de départ simulé pour le paper trading. Entier positif (0 < x < 2 147 483 647)."
              :model-value="form.paper_initial_capital"
              type="number"
              :min="1"
              :max="2147483646"
              :step="1"
              @update:model-value="form.paper_initial_capital = Number($event)"
            />
          </template>

          <!-- Live-specific -->
          <template v-if="form.run_type === 'live'">
            <div>
              <p class="text-xs text-gray-500 mb-1">
                Le capital initial est récupéré automatiquement depuis le solde du compte Binance au démarrage (non configurable).
              </p>
            </div>
            <div>
              <label for="network" class="block text-sm font-medium text-gray-700 mb-1">
                Réseau
              </label>
              <select
                id="network"
                v-model="network"
                class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="testnet">Testnet (sans risque)</option>
                <option value="mainnet">Mainnet (ARGENT RÉEL)</option>
              </select>
              <p class="mt-1 text-xs text-gray-500">
                Le testnet et le mainnet partagent le même verrou (un seul run live à la fois)
              </p>
            </div>

            <!-- Mainnet hard confirm -->
            <div v-if="network === 'mainnet'" class="rounded-md border border-red-300 bg-red-50 p-3">
              <p class="text-sm font-medium text-red-800 mb-2">
                ⚠️ Trading réel sur MAINNET — argent réel engagé.
              </p>
              <label for="confirm-phrase" class="block text-xs text-red-700 mb-1">
                Tapez exactement <span class="font-mono font-bold">I UNDERSTAND</span> pour confirmer
              </label>
              <input
                id="confirm-phrase"
                v-model="form.confirm_phrase"
                type="text"
                autocomplete="off"
                placeholder="I UNDERSTAND"
                class="w-full px-3 py-2 border border-red-300 rounded-md shadow-sm focus:outline-none focus:ring-red-500 focus:border-red-500"
              />
            </div>
          </template>

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
              :class="[
                'flex-1 px-4 py-2 rounded-md text-white transition-colors disabled:bg-gray-400',
                isMainnet ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700',
              ]"
            >
              {{ isLoading ? 'Démarrage...' : submitLabel }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ConfigField from '@/components/common/ConfigField.vue'
import { getSymbols } from '@/api/runs'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'
import type { StartRunRequest, StartRunType } from '@/api/types'

useBodyScrollLock()

interface Props {
  isLoading?: boolean
}
withDefaults(defineProps<Props>(), { isLoading: false })

const emit = defineEmits<{
  close: []
  launch: [payload: StartRunRequest]
}>()

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']
const MAINNET_PHRASE = 'I UNDERSTAND'

const network = ref<'testnet' | 'mainnet'>('testnet')

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
  run_type: 'backtest' as StartRunType,
  symbol: 'BTCUSDC',
  timeframe: '15m',
  start_date: '',
  end_date: '',
  initial_capital: 10000,
  paper_initial_capital: 1000,
  engine: 'vectorbt' as 'vectorbt' | 'event_driven',
  weights_set_id: '',
  confirm_phrase: '',
})

// Clear the confirm phrase whenever we leave mainnet so it can't leak through.
watch(network, (n) => {
  if (n !== 'mainnet') form.confirm_phrase = ''
})

const isMainnet = computed(() => form.run_type === 'live' && network.value === 'mainnet')

const runTypeHelp = computed(() => {
  switch (form.run_type) {
    case 'backtest':
      return 'Test historique sur des données passées. Plusieurs backtests en parallèle possibles.'
    case 'paper':
      return 'Trading simulé en temps réel (testnet). Un seul run paper à la fois.'
    case 'live':
      return 'Trading réel (testnet ou mainnet). Un seul run live à la fois.'
    default:
      return ''
  }
})

const submitLabel = computed(() => (isMainnet.value ? 'Démarrer (MAINNET)' : 'Démarrer'))

const canSubmit = computed(() => {
  if (!form.symbol || !form.timeframe) return false
  if (form.run_type === 'backtest') {
    const cap = Number(form.initial_capital)
    return (
      !!form.start_date &&
      !!form.end_date &&
      form.end_date > form.start_date &&
      Number.isInteger(cap) &&
      cap > 0 &&
      cap < 2147483647
    )
  }
  if (form.run_type === 'paper') {
    const cap = Number(form.paper_initial_capital)
    return Number.isInteger(cap) && cap > 0 && cap < 2147483647
  }
  if (form.run_type === 'live' && network.value === 'mainnet') {
    return form.confirm_phrase === MAINNET_PHRASE
  }
  return true
})

function handleSubmit() {
  if (!canSubmit.value) return

  const payload: StartRunRequest = {
    run_type: form.run_type,
    symbol: form.symbol,
    timeframe: form.timeframe,
  }

  if (form.run_type === 'backtest') {
    payload.start_date = form.start_date
    payload.end_date = form.end_date
    payload.initial_capital = Number(form.initial_capital)
    payload.engine = form.engine
    payload.save = true
    if (form.weights_set_id.trim()) payload.weights_set_id = form.weights_set_id.trim()
  } else if (form.run_type === 'paper') {
    payload.initial_capital = Number(form.paper_initial_capital)
  } else if (form.run_type === 'live') {
    payload.testnet = network.value === 'testnet'
    if (network.value === 'mainnet') payload.confirm_phrase = form.confirm_phrase
  }

  emit('launch', payload)
}
</script>
