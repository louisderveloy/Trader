<template>
  <div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center px-4">
    <div class="max-w-md w-full text-center">
      <!-- 404 Illustration -->
      <div class="mb-8">
        <div class="text-9xl font-bold text-gray-300 mb-2">404</div>
      </div>

      <!-- Error Message -->
      <h1 class="text-4xl font-bold text-gray-900 mb-4">
        Page non trouvée
      </h1>
      <p class="text-lg text-gray-600 mb-8">
        Désolé, la page que vous recherchez n'existe pas ou a été supprimée.
      </p>

      <!-- Return to Home Button -->
      <router-link
        to="/"
        class="inline-block bg-blue-600 text-white px-8 py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors mb-4 w-full"
      >
        Retour à l'accueil
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const currentRoute = computed(() => {
  return route.fullPath || '/'
})
</script>
