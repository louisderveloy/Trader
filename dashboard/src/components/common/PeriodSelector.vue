<template>
  <div class="flex flex-col md:flex-row gap-4 items-end">
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-2">
        Période
      </label>
      <select
        v-model="period"
        class="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
      >
        <option v-for="opt in options" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
    </div>

    <!-- Custom date range -->
    <div v-if="period === 'custom'" class="flex gap-4 flex-1">
      <div class="flex-1">
        <label class="block text-sm font-medium text-gray-700 mb-2">
          Du
        </label>
        <input
          v-model="customStart"
          type="date"
          class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        />
      </div>
      <div class="flex-1">
        <label class="block text-sm font-medium text-gray-700 mb-2">
          Au
        </label>
        <input
          v-model="customEnd"
          type="date"
          class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PERIOD_OPTIONS, type PeriodOption, type PeriodType } from '@/composables/usePeriodRange'

withDefaults(
  defineProps<{
    options?: PeriodOption[]
  }>(),
  {
    options: () => PERIOD_OPTIONS
  }
)

const period = defineModel<PeriodType>('period', { required: true })
const customStart = defineModel<string>('customStart', { default: '' })
const customEnd = defineModel<string>('customEnd', { default: '' })
</script>
