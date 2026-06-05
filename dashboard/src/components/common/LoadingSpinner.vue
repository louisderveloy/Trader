<template>
  <div class="flex items-center justify-center">
    <div
      class="animate-spin rounded-full border-t-2 border-b-2 border-primary-600"
      :class="sizeClass"
      role="status"
      aria-label="Loading"
    >
      <span class="sr-only">Chargement...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
})

const sizeClass = computed(() => {
  const sizes = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  }
  return sizes[props.size]
})
</script>
