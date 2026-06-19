import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  Config,
  RiskConfig,
  StrategyConfig,
  StopLossTakeProfitConfig,
  UserIndicator,
  getConfig,
  updateRiskConfig,
  updateStrategyConfig,
  updateStopLossTakeProfitConfig,
  getUserIndicator,
  updateUserIndicator
} from '@/api/config'

export const useConfigStore = defineStore('config', () => {
  // State
  const config = ref<Config | null>(null)
  const userIndicator = ref<UserIndicator | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const strategy = computed(() => config.value?.strategy)
  const risk = computed(() => config.value?.risk)
  const stopLossTakeProfit = computed(() => config.value?.stop_loss_take_profit)
  const indicators = computed(() => config.value?.indicators)
  const binance = computed(() => config.value?.binance)

  // Actions
  async function fetchConfig(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      config.value = await getConfig()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch configuration'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function updateStrategy(updates: Partial<StrategyConfig>): Promise<void> {
    error.value = null
    try {
      const updated = await updateStrategyConfig(updates)
      if (config.value) {
        config.value.strategy = updated
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update strategy configuration'
      throw err
    }
  }

  async function updateRisk(updates: Partial<RiskConfig>): Promise<void> {
    error.value = null
    try {
      const updated = await updateRiskConfig(updates)
      if (config.value) {
        config.value.risk = updated
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update risk configuration'
      throw err
    }
  }

  async function updateStopLossTakeProfit(updates: Partial<StopLossTakeProfitConfig>): Promise<void> {
    error.value = null
    try {
      const updated = await updateStopLossTakeProfitConfig(updates)
      if (config.value) {
        config.value.stop_loss_take_profit = updated
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update stop-loss/take-profit configuration'
      throw err
    }
  }

  async function fetchUserIndicator(symbol: string = 'BTCUSDT'): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      userIndicator.value = await getUserIndicator(symbol)
    } catch (err) {
      // Don't throw - user indicator might not exist yet
      error.value = err instanceof Error ? err.message : 'Failed to fetch user indicator'
      userIndicator.value = null
    } finally {
      isLoading.value = false
    }
  }

  async function updateIndicator(
    symbol: string,
    signal: number,
    note?: string,
    expires_in_hours?: number
  ): Promise<void> {
    error.value = null
    try {
      userIndicator.value = await updateUserIndicator(symbol, signal, note, expires_in_hours)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update user indicator'
      throw err
    }
  }

  return {
    // State
    config,
    userIndicator,
    isLoading,
    error,

    // Computed
    strategy,
    risk,
    stopLossTakeProfit,
    indicators,
    binance,

    // Actions
    fetchConfig,
    updateStrategy,
    updateRisk,
    updateStopLossTakeProfit,
    fetchUserIndicator,
    updateIndicator
  }
})
