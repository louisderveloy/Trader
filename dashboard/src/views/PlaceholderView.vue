<template>
  <AppLayout>
    <div class="max-w-4xl mx-auto">
      <EmptyState
        title="Page en développement"
        message="Cette page sera disponible dans les prochaines versions (Wave 2-3). Nous travaillons dessus !"
      >
        <button
          @click="router.push('/')"
          class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
        >
          Retour à l'accueil
        </button>
      </EmptyState>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const router = useRouter()
</script>
