/// <reference types="vite/client" />

/**
 * TypeScript definitions for Vite environment variables
 */

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_GRAFANA_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * Vue component type shim
 */
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
