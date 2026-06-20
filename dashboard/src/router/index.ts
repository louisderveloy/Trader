/**
 * Vue Router configuration with authentication guards
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { RouteRecordRaw } from 'vue-router'

// Route definitions
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false },
  },
  {
    // Authenticated-but-unauthorised landing (no Authelia group mapped).
    path: '/no-access',
    name: 'no-access',
    component: () => import('@/views/NoAccessView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/runs',
    name: 'runs',
    component: () => import('@/views/RunsView.vue'),
    meta: { requiresAuth: true },
  },
  // Wave 2: Configuration & User Indicator
  {
    path: '/configuration',
    name: 'configuration',
    component: () => import('@/views/ConfigurationView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/user-indicator',
    name: 'user-indicator',
    component: () => import('@/views/UserIndicatorView.vue'),
    meta: { requiresAuth: true },
  },
  // Wave 3: Optimizations, Trades
  {
    path: '/optimizations',
    name: 'optimizations',
    component: () => import('@/views/OptimizationsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/trades',
    name: 'trades',
    component: () => import('@/views/TradesView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { requiresAuth: true },
  },
  // Catch-all for 404
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { requiresAuth: false },
  },
]

// Create router instance
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Hydrate auth state exactly once, before the first route is resolved. Without this
// the guard would decide on stale state (user still null) on a fresh page load — e.g.
// after the Authelia OIDC redirect — and wrongly bounce an authenticated user to /login.
let authReady = false

/**
 * Navigation guard: Check authentication before each route
 */
router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // First navigation after a full page load: fetch /auth/me before deciding.
  if (!authReady) {
    authReady = true
    await authStore.initialize()
  }

  // Check if route requires authentication
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    // Redirect to login, save original destination
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && authStore.isAuthenticated) {
    // Already authenticated: restore last route or go home. Only accept a
    // same-origin relative path (security review #14): must start with a single
    // '/', reject protocol-relative '//host' (open redirect) and '/login'.
    const lastRoute = localStorage.getItem('lastRoute')
    const isSafe =
      !!lastRoute &&
      lastRoute.startsWith('/') &&
      !lastRoute.startsWith('//') &&
      lastRoute !== '/login'
    return isSafe ? lastRoute : { name: 'home' }
  }

  // Allow navigation
  return true
})

/**
 * Save current route to localStorage after each navigation
 * This allows restoring the user's location after page reload
 */
router.afterEach((to) => {
  // Only save authenticated routes (not login or 404)
  if (to.meta.requiresAuth && to.name !== 'not-found') {
    localStorage.setItem('lastRoute', to.fullPath)
  }
})

export default router
