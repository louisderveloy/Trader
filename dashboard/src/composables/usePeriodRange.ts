/**
 * Shared time-period selection logic for dashboard views.
 *
 * Exposes the canonical list of period options and a pure helper that converts
 * a selected period (and optional custom dates) into a concrete date range.
 * HomeView and TradesView both build on this so the available periods stay in
 * sync (see issues #11 and #12).
 */

export type PeriodType = 'all' | 'day' | 'week' | 'month' | 'quarter' | 'year' | 'custom'

export interface PeriodOption {
  value: PeriodType
  label: string
}

/** Periods offered on the home dashboard (no "all" — it always scopes a range). */
export const PERIOD_OPTIONS: PeriodOption[] = [
  { value: 'day', label: 'Dernier 24h' },
  { value: 'week', label: 'Dernière semaine' },
  { value: 'month', label: 'Dernier mois' },
  { value: 'quarter', label: 'Dernier trimestre' },
  { value: 'year', label: 'Dernière année' },
  { value: 'custom', label: 'Personnalisé' }
]

/** Periods offered on the trades history view: same set plus "Tout" (no filter). */
export const PERIOD_OPTIONS_WITH_ALL: PeriodOption[] = [
  { value: 'all', label: 'Tout' },
  ...PERIOD_OPTIONS
]

export interface DateRange {
  /** Inclusive lower bound, or null when the period is unbounded ("all"). */
  startDate: Date | null
  /** Inclusive upper bound, or null when the period is unbounded ("all"). */
  endDate: Date | null
}

const DAYS_BY_PERIOD: Partial<Record<PeriodType, number>> = {
  day: 1,
  week: 7,
  month: 30,
  quarter: 90,
  year: 365
}

/**
 * Resolve a period selection into a concrete date range.
 *
 * - Rolling periods (day/week/month/quarter/year) end "now" and start N days back.
 * - "custom" uses the provided ISO date strings; if either is missing the range
 *   is treated as unbounded so nothing is hidden while the user is still typing.
 * - "all" returns a fully open range (no date filtering).
 */
export function getPeriodRange(
  period: PeriodType,
  customStart?: string,
  customEnd?: string
): DateRange {
  if (period === 'all') {
    return { startDate: null, endDate: null }
  }

  if (period === 'custom') {
    if (!customStart || !customEnd) {
      return { startDate: null, endDate: null }
    }
    return {
      startDate: new Date(customStart),
      endDate: new Date(customEnd)
    }
  }

  const days = DAYS_BY_PERIOD[period]
  if (days === undefined) {
    return { startDate: null, endDate: null }
  }

  const endDate = new Date()
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - days)
  return { startDate, endDate }
}
