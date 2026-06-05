<template>
  <header class="bg-white shadow-sm border-b border-gray-200">
    <div class="px-4 py-3 flex items-center justify-between">
      <!-- Left: Hamburger menu + Title -->
      <div class="flex items-center space-x-4">
        <!-- Hamburger menu (mobile) -->
        <button
          @click="uiStore.toggleSidebar"
          class="lg:hidden text-gray-600 hover:text-gray-900 focus:outline-none"
          aria-label="Toggle sidebar"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>

        <!-- Title -->
        <h1 class="text-xl font-bold text-gray-900">Trading Bot Dashboard</h1>
      </div>

      <!-- Right: User info + Logout -->
      <div class="flex items-center space-x-4">
        <!-- User info -->
        <div class="hidden sm:flex items-center space-x-2 text-sm text-gray-600">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
          <span class="font-medium">{{ authStore.user?.username || 'User' }}</span>
        </div>

        <!-- Logout button -->
        <button
          @click="handleLogout"
          class="px-3 py-1.5 text-sm text-gray-700 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          Déconnexion
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>
