<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Header -->
    <AppHeader />

    <div class="flex">
      <!-- Sidebar -->
      <AppSidebar />

      <!-- Main content -->
      <main class="flex-1 p-6 lg:p-8 lg:ml-64">
        <slot />
      </main>
    </div>

    <!-- Toast Notifications -->
    <div class="toast-container">
      <ToastNotification
        v-for="toast in toastStore.toasts"
        :key="toast.id"
        :message="toast.message"
        :type="toast.type"
        :duration="toast.duration"
        @close="toastStore.remove(toast.id)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import ToastNotification from '@/components/common/ToastNotification.vue'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()
</script>
