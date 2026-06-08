/**
 * Main entry point for the Trading Bot Dashboard
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './style.css'
import { useAuthStore } from './stores/auth'
import { fetchCsrfToken } from './api/client'

// Create Vue app
const app = createApp(App)

// Use plugins
const pinia = createPinia()
app.use(pinia)
app.use(router)

// Initialize authentication state
// Attempts to fetch current user if httpOnly cookie exists
const authStore = useAuthStore()
authStore.initialize().then(() => {
  // After auth initialization, restore last route if user is authenticated
  if (authStore.isAuthenticated) {
    const lastRoute = localStorage.getItem('lastRoute')
    if (lastRoute && lastRoute !== '/login' && router.currentRoute.value.path === '/') {
      router.replace(lastRoute)
    }
  }
})

// Fetch CSRF token for state-changing requests
// Token is stored in cookie and automatically included in POST/PATCH/PUT/DELETE requests
fetchCsrfToken()

// Mount app
app.mount('#app')
