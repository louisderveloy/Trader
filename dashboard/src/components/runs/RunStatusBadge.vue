<template>
  <span
    :class="[
      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
      statusConfig.color,
      statusConfig.bgColor,
    ]"
  >
    {{ statusConfig.label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RUN_STATUS_CONFIG } from '@/utils/constants'
import type { RunStatus } from '@/utils/constants'

interface Props {
  status: string
}

const props = defineProps<Props>()

const statusConfig = computed(() => {
  return (
    RUN_STATUS_CONFIG[props.status as RunStatus] || {
      label: props.status,
      color: 'text-gray-800',
      bgColor: 'bg-gray-100',
    }
  )
})
</script>
