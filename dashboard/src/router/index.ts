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

/**
 * Navigation guard: Check authentication before each route
 */
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  // Check if route requires authentication
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    // Redirect to login, save original destination
    next({
      name: 'login',
      query: { redirect: to.fullPath },
    })
  } else if (to.name === 'login' && authStore.isAuthenticated) {
    // Already authenticated, redirect to home
    next({ name: 'home' })
  } else {
    // Allow navigation
    next()
  }
})

export default router
