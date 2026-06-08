/**
 * Toast notification store for showing success/error messages
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
  duration?: number
}

export const useToastStore = defineStore('toast', () => {
  // State
  const toasts = ref<Toast[]>([])
  let nextId = 0

  // Actions
  /**
   * Show a success toast notification
   */
  function success(message: string, duration = 4000) {
    const toast: Toast = {
      id: nextId++,
      message,
      type: 'success',
      duration,
    }
    toasts.value.push(toast)
  }

  /**
   * Show an error toast notification
   */
  function error(message: string, duration = 4000) {
    const toast: Toast = {
      id: nextId++,
      message,
      type: 'error',
      duration,
    }
    toasts.value.push(toast)
  }

  /**
   * Remove a toast by ID
   */
  function remove(id: number) {
    const index = toasts.value.findIndex((t) => t.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
    }
  }

  /**
   * Clear all toasts
   */
  function clear() {
    toasts.value = []
  }

  return {
    // State
    toasts,
    // Actions
    success,
    error,
    remove,
    clear,
  }
})
