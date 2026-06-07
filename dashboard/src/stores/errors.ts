/**
 * Errors store - manages error logs state and API calls
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as errorsApi from '@/api/errors'
import type { ErrorLog, ErrorStats, ErrorFilters } from '@/api/errors'

export const useErrorsStore = defineStore('errors', () => {
  // State
  const errors = ref<ErrorLog[]>([])
  const stats = ref<ErrorStats | null>(null)
  const categories = ref<string[]>([])
  const total = ref(0)
  const limit = ref(50)
  const offset = ref(0)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Fetch error logs with filters
   */
  async function fetchErrors(filters: ErrorFilters = {}): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const params: ErrorFilters = {
        ...filters,
        limit: filters.limit || limit.value,
        offset: filters.offset || offset.value,
      }

      const response = await errorsApi.listErrors(params)
      errors.value = response.items
      total.value = response.total
      limit.value = response.limit
      offset.value = response.offset
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch errors'
      console.error('Error fetching errors:', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch error statistics
   */
  async function fetchStats(): Promise<void> {
    try {
      const response = await errorsApi.getErrorStats()
      stats.value = response
    } catch (err: any) {
      console.error('Error fetching stats:', err)
    }
  }

  /**
   * Fetch available error categories
   */
  async function fetchCategories(): Promise<void> {
    try {
      const response = await errorsApi.getErrorCategories()
      categories.value = response
    } catch (err: any) {
      console.error('Error fetching categories:', err)
    }
  }

  /**
   * Get error by ID
   */
  async function getErrorById(id: string): Promise<ErrorLog | null> {
    try {
      return await errorsApi.getError(id)
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch error'
      console.error('Error fetching error:', err)
      return null
    }
  }

  /**
   * Pagination: next page
   */
  function nextPage(): void {
    if (offset.value + limit.value < total.value) {
      offset.value += limit.value
    }
  }

  /**
   * Pagination: previous page
   */
  function previousPage(): void {
    if (offset.value > 0) {
      offset.value = Math.max(0, offset.value - limit.value)
    }
  }

  return {
    // State
    errors,
    stats,
    categories,
    total,
    limit,
    offset,
    isLoading,
    error,
    // Actions
    fetchErrors,
    fetchStats,
    fetchCategories,
    getErrorById,
    nextPage,
    previousPage,
  }
})
