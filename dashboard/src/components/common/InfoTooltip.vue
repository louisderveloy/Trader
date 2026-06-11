<template>
  <!-- Standalone "?" tooltip for fields that aren't ConfigField (e.g. selects). -->
  <div class="relative inline-block">
    <button
      type="button"
      class="w-5 h-5 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-xs font-bold hover:bg-blue-300 transition-colors"
      @mouseenter="show = true"
      @mouseleave="show = false"
      @focus="show = true"
      @blur="show = false"
    >
      ?
    </button>
    <div
      v-if="show"
      class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg w-60 z-20"
    >
      {{ text }}
      <div
        class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ text: string }>()

const show = ref(false)
</script>
