<template>
  <div class="mb-4">
    <div class="flex items-center gap-2 mb-2">
      <label :for="id" class="block text-sm font-medium text-gray-700">
        {{ label }}
      </label>
      <!-- Tooltip with French explanation (mandatory per CLAUDE.md).
           Rendered via InfoTooltip (teleported to body, clamped on-screen) so it
           is never clipped by a modal's overflow. -->
      <InfoTooltip :text="tooltip" />
    </div>

    <!-- Select field (when options are provided) -->
    <select
        v-if="options"
        :id="id"
        :value="modelValue"
        :disabled="disabled"
        class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
        @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>

    <!-- Input field -->
    <input
        v-else
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
import InfoTooltip from '@/components/common/InfoTooltip.vue'

interface Props {
  id: string
  label: string
  tooltip: string // French tooltip (mandatory)
  modelValue: string | number
  type?: 'text' | 'number' | 'email' | 'password' | 'date'
  disabled?: boolean
  helpText?: string
  min?: number
  max?: number
  step?: number | string
  options?: { value: string; label: string }[]
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  disabled: false,
  min: undefined,
  max: undefined,
  step: undefined,
  options: undefined
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

function getInputValue(event: Event): string | number {
  const target = event.target as HTMLInputElement
  if (props.type === 'number') {
    // Handle empty input
    if (target.value === '') {
      return ''
    }

    // Parse the value
    const numValue = parseFloat(target.value)

    // If parseFloat returns NaN, it means we're in the middle of typing
    // a number (e.g., "-", ".", "-.", "1."). Keep the string value.
    if (isNaN(numValue)) {
      return target.value
    }

    // Return the parsed number
    return numValue
  }
  return target.value
}
</script>
