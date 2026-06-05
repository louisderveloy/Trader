/**
 * Application constants
 */

// Run types
export const RUN_TYPES = {
  BACKTEST: 'backtest',
  OPTIMIZATION: 'optimization',
  PAPER: 'paper',
  LIVE: 'live',
} as const

export type RunType = (typeof RUN_TYPES)[keyof typeof RUN_TYPES]

// Run statuses
export const RUN_STATUSES = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const

export type RunStatus = (typeof RUN_STATUSES)[keyof typeof RUN_STATUSES]

// Polling intervals (milliseconds)
export const POLLING_INTERVALS = {
  ACTIVE_RUNS: 10000, // 10 seconds
  TRADES: 30000, // 30 seconds
  CONFIG: 60000, // 1 minute
} as const

// Run status display configuration
export const RUN_STATUS_CONFIG: Record<
  RunStatus,
  { label: string; color: string; bgColor: string }
> = {
  pending: {
    label: 'En attente',
    color: 'text-yellow-800',
    bgColor: 'bg-yellow-100',
  },
  running: {
    label: 'En cours',
    color: 'text-blue-800',
    bgColor: 'bg-blue-100',
  },
  completed: {
    label: 'Complété',
    color: 'text-green-800',
    bgColor: 'bg-green-100',
  },
  failed: {
    label: 'Échoué',
    color: 'text-red-800',
    bgColor: 'bg-red-100',
  },
  cancelled: {
    label: 'Annulé',
    color: 'text-gray-800',
    bgColor: 'bg-gray-100',
  },
}

// Run type display configuration
export const RUN_TYPE_CONFIG: Record<RunType, { label: string }> = {
  backtest: { label: 'Backtest' },
  optimization: { label: 'Optimisation' },
  paper: { label: 'Paper Trading' },
  live: { label: 'Live' },
}
