/**
 * Formatting utilities for dates, numbers, and currencies
 */

import { format, formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'

/**
 * Format date as dd/MM/yyyy HH:mm
 */
export function formatDate(date: string | Date): string {
  return format(new Date(date), 'dd/MM/yyyy HH:mm', { locale: fr })
}

/**
 * Format date as dd/MM/yyyy (short)
 */
export function formatDateShort(date: string | Date): string {
  return format(new Date(date), 'dd/MM/yyyy', { locale: fr })
}

/**
 * Format relative time (e.g., "il y a 2 heures")
 */
export function formatRelativeTime(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true, locale: fr })
}

/**
 * Format number with specified decimals
 */
export function formatNumber(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/**
 * Format as percentage (e.g., "12.34%")
 */
export function formatPercent(value: number, decimals: number = 2): string {
  return `${formatNumber(value, decimals)}%`
}

/**
 * Format as currency (e.g., "1234.56 USDT")
 */
export function formatCurrency(value: number, currency: string = 'USDT'): string {
  return `${formatNumber(value, 2)} ${currency}`
}
