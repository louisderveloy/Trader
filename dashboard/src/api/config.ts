/**
Configuration API endpoints.

API client functions for reading and updating bot configuration.
**/

import { apiClient } from './client'

export interface StrategyConfig {
  entry_threshold: number
  exit_threshold: number
  confirmation_candles: number
}

export interface RiskConfig {
  max_trades_per_day: number
  max_exposure_percent: number
  position_size_mode: 'fixed' | 'confidence' | 'risk_atr'
  fixed_size_percent: number
  atr_multiplier: number
  capital_risk_percent: number
}

export interface StopLossTakeProfitConfig {
  sl_mode: 'atr' | 'fixed'
  sl_atr_multiplier: number
  sl_fixed_percent: number
  tp_mode: 'atr' | 'fixed'
  tp_atr_multiplier: number
  tp_fixed_percent: number
}

export interface BinanceConfig {
  symbol: string
  timeframe: string
  max_slippage_percent: number
  order_timeout_seconds: number
}

export interface IndicatorConfig {
  name: string
  enabled: boolean
  parameters: Record<string, unknown>
  description?: string
}

export interface Config {
  binance: BinanceConfig
  strategy: StrategyConfig
  risk: RiskConfig
  stop_loss_take_profit: StopLossTakeProfitConfig
  indicators: Record<string, IndicatorConfig>
}

export interface UserIndicator {
  symbol: string
  signal: number | null
  note?: string
  expires_at: string | null
  status: 'ValueSet' | 'ValueNotSet'
}

/**
 * Get complete bot configuration
 */
export async function getConfig(): Promise<Config> {
  const response = await apiClient.get<Config>('/config')
  return response.data
}

/**
 * Update strategy configuration
 */
export async function updateStrategyConfig(config: Partial<StrategyConfig>): Promise<StrategyConfig> {
  const response = await apiClient.patch<StrategyConfig>('/config/strategy', config)
  return response.data
}

/**
 * Update risk configuration
 */
export async function updateRiskConfig(config: Partial<RiskConfig>): Promise<RiskConfig> {
  const response = await apiClient.patch<RiskConfig>('/config/risk', config)
  return response.data
}

/**
 * Update stop-loss/take-profit configuration
 */
export async function updateStopLossTakeProfitConfig(
  config: Partial<StopLossTakeProfitConfig>
): Promise<StopLossTakeProfitConfig> {
  const response = await apiClient.patch<StopLossTakeProfitConfig>('/config/stop-loss-take-profit', config)
  return response.data
}

/**
 * Get user indicator for a symbol
 */
export async function getUserIndicator(symbol: string = 'BTCUSDC'): Promise<UserIndicator> {
  const response = await apiClient.get<UserIndicator>('/config/user-indicator', {
    params: { symbol }
  })
  return response.data
}

/**
 * Update user indicator for a symbol
 */
export async function updateUserIndicator(
  symbol: string,
  signal: number,
  note?: string,
  expires_in_hours: number = 24
): Promise<UserIndicator> {
  const response = await apiClient.patch<UserIndicator>(
    '/config/user-indicator',
    {
      signal,
      note,
      expires_in_hours
    },
    {
      params: { symbol }
    }
  )
  return response.data
}
