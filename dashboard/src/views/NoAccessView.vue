<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 px-4">
    <div class="max-w-md w-full">
      <div class="bg-white rounded-lg shadow-lg p-8 text-center">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-100">
          <svg class="h-6 w-6 text-amber-600" fill="none" viewBox="0 0 24 24" stroke-width="1.5"
               stroke="currentColor" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
        </div>
        <h1 class="mt-4 text-2xl font-bold text-gray-900">Accès non autorisé</h1>
        <p class="mt-3 text-gray-600">
          Votre compte est authentifié mais n'a pas les droits nécessaires pour accéder à ce
          tableau de bord.
        </p>
        <p class="mt-2 text-gray-600">
          Si vous pensez devoir y avoir accès, veuillez contacter le propriétaire du site.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Intentionally static: no API calls, no information about why access was denied.
</script>
