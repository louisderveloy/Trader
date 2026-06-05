<template>
  <div class="mb-4">
    <div class="flex items-center gap-2 mb-2">
      <label :for="id" class="block text-sm font-medium text-gray-700">
        {{ label }}
      </label>
      <!-- Tooltip with French explanation (mandatory per CLAUDE.md) -->
      <div class="relative group inline-block">
        <button
          type="button"
          class="w-5 h-5 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-xs font-bold hover:bg-blue-300 transition-colors"
          @mouseenter="showTooltip = true"
          @mouseleave="showTooltip = false"
          @focus="showTooltip = true"
          @blur="showTooltip = false"
        >
          ?
        </button>
        <!-- Tooltip popover -->
        <div
          v-if="showTooltip"
          class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg whitespace-nowrap z-10"
        >
          {{ tooltip }}
          <div class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
        </div>
      </div>
    </div>

    <!-- Input field -->
    <input
      :id="id"
      :type="type"
      :value="modelValue"
      :disabled="disabled"
      :min="min"
      :max="max"
      :step="step"
      class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
      @input="emit('update:modelValue', getInputValue($event))"
    />

    <!-- Help text (optional) -->
    <p v-if="helpText" class="mt-1 text-sm text-gray-500">
      {{ helpText }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Props {
  id: string
  label: string
  tooltip: string // French tooltip (mandatory)
  modelValue: string | number
  type?: 'text' | 'number' | 'email' | 'password'
  disabled?: boolean
  helpText?: string
  min?: number
  max?: number
  step?: number | string
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  disabled: false,
  min: undefined,
  max: undefined,
  step: undefined
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const showTooltip = ref(false)

function getInputValue(event: Event): string | number {
  const target = event.target as HTMLInputElement
  if (props.type === 'number') {
    return target.value === '' ? 0 : parseFloat(target.value)
  }
  return target.value
}
</script>
