<template>
  <!-- Modal Backdrop -->
  <div class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4">
    <!-- Modal Content -->
    <div class="bg-white rounded-lg shadow-lg max-w-md w-full">
      <div class="p-6">
        <!-- Header -->
        <h2 class="text-xl font-bold text-gray-900 mb-4">Lancer Optimisation</h2>

        <!-- Form -->
        <form @submit.prevent="handleSubmit" class="space-y-4">
          <!-- Name -->
          <div>
            <label for="study-name" class="block text-sm font-medium text-gray-700 mb-1">
              Nom de l'étude
            </label>
            <input
              id="study-name"
              v-model="formData.name"
              type="text"
              placeholder="Ex: Optuna Study 2024-01-15"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <!-- Objective -->
          <div>
            <label for="objective" class="block text-sm font-medium text-gray-700 mb-1">
              Objectif d'optimisation
            </label>
            <select
              id="objective"
              v-model="formData.objective"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="sharpe">Sharpe Ratio</option>
              <option value="sortino">Sortino Ratio</option>
              <option value="profit_factor">Profit Factor</option>
            </select>
            <p class="mt-1 text-xs text-gray-500">
              Métrique à maximiser pour évaluer les paramètres
            </p>
          </div>

          <!-- Number of Trials -->
          <div>
            <label for="n-trials" class="block text-sm font-medium text-gray-700 mb-1">
              Nombre d'essais
            </label>
            <input
              id="n-trials"
              v-model.number="formData.n_trials"
              type="number"
              :min="10"
              :max="1000"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            <p class="mt-1 text-xs text-gray-500">
              Plus d'essais = meilleurs résultats mais plus long
            </p>
          </div>

          <!-- Number of Jobs -->
          <div>
            <label for="n-jobs" class="block text-sm font-medium text-gray-700 mb-1">
              Tâches parallèles
            </label>
            <input
              id="n-jobs"
              v-model.number="formData.n_jobs"
              type="number"
              :min="1"
              :max="8"
              class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            <p class="mt-1 text-xs text-gray-500">
              Nombre de processeurs à utiliser (1-8)
            </p>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 pt-4">
            <button
              type="button"
              @click="$emit('close')"
              class="flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              :disabled="isLoading || !formData.name"
              class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
            >
              {{ isLoading ? 'Lancement...' : 'Lancer' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Props {
  isLoading?: boolean
}

withDefaults(defineProps<Props>(), {
  isLoading: false
})

const emit = defineEmits<{
  close: []
  launch: [data: { name: string; objective: string; n_trials: number; n_jobs: number }]
}>()

const formData = ref({
  name: '',
  objective: 'sharpe',
  n_trials: 100,
  n_jobs: 1
})

function handleSubmit() {
  if (formData.value.name.trim()) {
    emit('launch', formData.value)
    formData.value = {
      name: '',
      objective: 'sharpe',
      n_trials: 100,
      n_jobs: 1
    }
  }
}
</script>
