<template>
  <div class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4">
    <div class="bg-white rounded-lg shadow-lg max-w-3xl w-full max-h-[90vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-gray-200">
        <h2 class="text-lg font-bold text-gray-900">Logs — Run #{{ runId }}</h2>
        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="load"
            :disabled="isLoading"
            class="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {{ isLoading ? '...' : 'Rafraîchir' }}
          </button>
          <button
            type="button"
            @click="$emit('close')"
            class="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
          >
            Fermer
          </button>
        </div>
      </div>

      <!-- Body -->
      <div class="p-4 overflow-auto flex-1">
        <p v-if="truncated" class="text-xs text-amber-600 mb-2">
          Affichage des dernières lignes uniquement (les plus anciennes sont tronquées).
        </p>
        <pre
          v-if="lines.length"
          class="text-xs font-mono bg-gray-900 text-gray-100 rounded-md p-3 whitespace-pre-wrap break-words"
        >{{ lines.join('\n') }}</pre>
        <p v-else-if="!isLoading" class="text-sm text-gray-500 text-center py-8">
          Aucun log disponible pour ce run.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRunsStore } from '@/stores/runs'

interface Props {
  runId: number
}
const props = defineProps<Props>()
defineEmits<{ close: [] }>()

const runsStore = useRunsStore()
const lines = ref<string[]>([])
const truncated = ref(false)
const isLoading = ref(false)

async function load() {
  isLoading.value = true
  try {
    const res = await runsStore.fetchLogs(props.runId)
    if (res) {
      lines.value = res.lines
      truncated.value = res.truncated
    }
  } finally {
    isLoading.value = false
  }
}

onMounted(load)
</script>
