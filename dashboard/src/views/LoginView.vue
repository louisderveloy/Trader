<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 px-4">
    <div class="max-w-md w-full space-y-8">
      <!-- Card -->
      <div class="bg-white rounded-lg shadow-lg p-8">
        <!-- Header -->
        <div class="text-center">
          <h2 class="text-3xl font-bold text-gray-900">Trading Bot Dashboard</h2>
          <p class="mt-2 text-gray-600">
            Connectez-vous pour accéder au dashboard
          </p>
        </div>

        <!-- OIDC mode: redirect to Authelia (no password form in the dashboard) -->
        <div v-if="authStore.oidcMode" class="mt-8 space-y-6">
          <button
              type="button"
              @click="handleOidcLogin"
              class="w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
          >
            Se connecter avec Authelia
          </button>
          <p class="text-center text-sm text-gray-500">
            Vous serez redirigé vers le fournisseur d'authentification.
          </p>
        </div>

        <!-- Local mode: built-in password form (dev only) -->
        <form v-else @submit.prevent="handleLogin" class="mt-8 space-y-6">
          <!-- Username field -->
          <div>
            <label for="username" class="block text-sm font-medium text-gray-700">
              Nom d'utilisateur
            </label>
            <input
                v-model="username"
                id="username"
                type="text"
                required
                autocomplete="username"
                class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                :disabled="authStore.isLoading"
            />
          </div>

          <!-- Password field -->
          <div>
            <label for="password" class="block text-sm font-medium text-gray-700">
              Mot de passe
            </label>
            <input
                v-model="password"
                id="password"
                type="password"
                required
                autocomplete="current-password"
                class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                :disabled="authStore.isLoading"
            />
          </div>

          <!-- Error message -->
          <ErrorAlert v-if="authStore.error" :message="authStore.error"/>

          <!-- Submit button -->
          <button
              type="submit"
              :disabled="authStore.isLoading || !username || !password"
              class="w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <LoadingSpinner v-if="authStore.isLoading" size="sm"/>
            <span v-else>Se connecter</span>
          </button>
        </form>

        <!-- Info (local/dev only) -->
        <div v-if="!authStore.oidcMode" class="mt-6 text-center text-sm text-gray-500">
          <p>Utilisateur par défaut: admin / admin</p>
          <p class="mt-1 text-xs">(configurable dans .env)</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {onMounted, ref} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {useAuthStore} from '@/stores/auth'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')

async function handleLogin() {
  const success = await authStore.login(username.value, password.value)

  if (success) {
    // Redirect to original destination or home
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  }
}

/** OIDC mode: full-page redirect to the API, which redirects to Authelia. */
function handleOidcLogin() {
  const redirect = (route.query.redirect as string) || '/'
  authStore.loginRedirect(redirect)
}

// Initialize auth store (fetch user if token exists)
onMounted(() => {
  authStore.initialize()
  if (authStore.isAuthenticated) {
    router.push('/')
  }
})
</script>
