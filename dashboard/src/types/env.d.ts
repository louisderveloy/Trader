/// <reference types="vite/client" />

/**
 * TypeScript definitions for Vite environment variables
 */

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_GRAFANA_BASE_URL?: string
  // Auth mode mirrors the API AUTH_MODE: 'local' (dev password form) or
  // 'authelia_oidc' (redirect to Authelia). Defaults to 'local' when unset.
  readonly VITE_AUTH_MODE?: 'local' | 'authelia_oidc'
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
