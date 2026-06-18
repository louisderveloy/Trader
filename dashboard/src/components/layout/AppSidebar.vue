<template>
  <!-- Overlay for mobile -->
  <div
      v-if="uiStore.sidebarOpen"
      @click="uiStore.closeSidebar"
      class="fixed inset-0 z-5 bg-black bg-opacity-50 lg:hidden"
  />

  <!-- Sidebar -->
  <aside
      :class="[
      'fixed top-[53px] bottom-0 left-0 z-6 w-64 bg-white border-r border-gray-200 transform transition-transform duration-300 ease-in-out overflow-y-auto',
      uiStore.sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
    ]"
  >
    <nav class="p-4 space-y-2 pb-8">
      <!-- Navigation links -->
      <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          :class="[
          'flex items-center space-x-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
          item.disabled
            ? 'text-gray-400 cursor-not-allowed'
            : route.path === item.path
            ? 'bg-primary-100 text-primary-700'
            : 'text-gray-700 hover:bg-gray-100',
        ]"
          :title="item.disabled ? 'Prochainement (Wave 2-3)' : undefined"
          @click="handleNavClick(item)"
      >
        <component :is="item.icon" class="w-5 h-5"/>
        <span>{{ item.label }}</span>
        <span v-if="item.disabled" class="ml-auto text-xs text-gray-400">Prochainement</span>
      </router-link>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import {computed, h} from 'vue'
import {useRoute} from 'vue-router'
import {useUiStore} from '@/stores/ui'

const route = useRoute()
const uiStore = useUiStore()

// Icons as functional components
const HomeIcon = () =>
    h('svg', {class: 'w-5 h-5', fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24'}, [
      h('path', {
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-width': '2',
        d: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
      }),
    ])

const RunsIcon = () =>
    h('svg', {class: 'w-5 h-5', fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24'}, [
      h('path', {
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-width': '2',
        d: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
      }),
    ])

const ConfigIcon = () =>
    h('svg', {class: 'w-5 h-5', fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24'}, [
      h('path', {
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-width': '2',
        d: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z',
      }),
      h('path', {
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-width': '2',
        d: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z',
      }),
    ])

const ChartIcon = () =>
    h('svg', {class: 'w-5 h-5', fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24'}, [
      h('path', {
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-width': '2',
        d: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
      }),
    ])

const ErrorsIcon = () =>
    h('svg', {class: 'w-5 h-5', fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24'}, [
      h('path', {
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'stroke-width': '2',
        d: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
      }),
    ])

// Navigation items
const navItems = computed(() => [
  {
    path: '/',
    label: 'Accueil',
    icon: HomeIcon,
    disabled: false,
  },
  {
    path: '/runs',
    label: 'Runs',
    icon: RunsIcon,
    disabled: false,
  },
  {
    path: '/configuration',
    label: 'Configuration',
    icon: ConfigIcon,
    disabled: false, // Wave 2 ✅ ACTIVE
  },
  {
    path: '/user-indicator',
    label: 'Indicateur Utilisateur',
    icon: ChartIcon,
    disabled: false, // Wave 2 ✅ ACTIVE
  },
  {
    path: '/optimizations',
    label: 'Optimisations',
    icon: ChartIcon,
    disabled: false, // Wave 3 ✅ ACTIVE
  },
  {
    path: '/trades',
    label: 'Trades',
    icon: ChartIcon,
    disabled: false, // Wave 3 ✅ ACTIVE
  },
  {
    path: '/logs',
    label: 'Logs & Erreurs',
    icon: ErrorsIcon,
    disabled: false,
  },
])

function handleNavClick(item: any) {
  if (item.disabled) {
    return false
  }
  // Close sidebar on mobile after navigation
  if (window.innerWidth < 1024) {
    uiStore.closeSidebar()
  }
}
</script>
