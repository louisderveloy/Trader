/**
 * UI state store for sidebar, modals, etc.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  // State
  const sidebarOpen = ref(true)

  // Actions
  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value
  }

  function closeSidebar(): void {
    sidebarOpen.value = false
  }

  function openSidebar(): void {
    sidebarOpen.value = true
  }

  return {
    // State
    sidebarOpen,
    // Actions
    toggleSidebar,
    closeSidebar,
    openSidebar,
  }
})
