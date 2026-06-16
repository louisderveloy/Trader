/**
 * Main entry point for the Trading Bot Dashboard
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './style.css'
import { fetchCsrfToken } from './api/client'

// Create Vue app
const app = createApp(App)

// Use plugins
const pinia = createPinia()
app.use(pinia)
app.use(router)

// Auth state is hydrated by the router guard (router/index.ts) before the first
// route resolves, so we must NOT race it here with an un-awaited initialize().

// Fetch CSRF token for state-changing requests
// Token is stored in cookie and automatically included in POST/PATCH/PUT/DELETE requests
fetchCsrfToken()

// Mount app
app.mount('#app')
