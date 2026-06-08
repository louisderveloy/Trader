<template>
  <Transition
    enter-active-class="transform transition duration-300 ease-out"
    enter-from-class="-translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transform transition duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="-translate-y-full opacity-0"
  >
    <div
      v-if="isVisible"
      :class="[
        'fixed top-4 left-1/2 -translate-x-1/2 z-50 min-w-80 max-w-md rounded-lg shadow-lg p-4',
        type === 'success' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
      ]"
    >
      <div class="flex items-start">
        <div class="flex-shrink-0">
          <!-- Success Icon -->
          <svg
            v-if="type === 'success'"
            class="h-5 w-5 text-green-400"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clip-rule="evenodd"
            />
          </svg>
          <!-- Error Icon -->
          <svg
            v-else
            class="h-5 w-5 text-red-400"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clip-rule="evenodd"
            />
          </svg>
        </div>
        <div class="ml-3 flex-1">
          <p
            :class="[
              'text-sm font-medium',
              type === 'success' ? 'text-green-800' : 'text-red-800'
            ]"
          >
            {{ message }}
          </p>
        </div>
        <div class="ml-4 flex-shrink-0">
          <button
            @click="close"
            :class="[
              'inline-flex rounded-md p-1.5 focus:outline-none focus:ring-2 focus:ring-offset-2',
              type === 'success'
                ? 'text-green-500 hover:bg-green-100 focus:ring-green-600'
                : 'text-red-500 hover:bg-red-100 focus:ring-red-600'
            ]"
          >
            <span class="sr-only">Fermer</span>
            <svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clip-rule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface Props {
  message: string
  type: 'success' | 'error'
  duration?: number
}

const props = withDefaults(defineProps<Props>(), {
  duration: 4000
})

const emit = defineEmits<{
  close: []
}>()

const isVisible = ref(true)
let timeoutId: number | null = null

function close() {
  isVisible.value = false
  setTimeout(() => {
    emit('close')
  }, 200) // Wait for exit animation
}

// Auto-close after duration
watch(
  () => props.message,
  () => {
    isVisible.value = true
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
    timeoutId = window.setTimeout(() => {
      close()
    }, props.duration)
  },
  { immediate: true }
)
</script>
