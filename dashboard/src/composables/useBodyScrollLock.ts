import { onMounted, onUnmounted } from 'vue'

/**
 * Lock background (document body) scrolling while a modal is mounted.
 *
 * Call this from a modal component that is rendered via `v-if` (so its
 * mount/unmount lifecycle matches the modal's visibility). A module-level
 * counter keeps the lock correct when more than one modal is open at once.
 */
let lockCount = 0
let savedOverflow = ''

export function useBodyScrollLock(): void {
  onMounted(() => {
    if (lockCount === 0) {
      savedOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    }
    lockCount += 1
  })

  onUnmounted(() => {
    lockCount = Math.max(0, lockCount - 1)
    if (lockCount === 0) {
      document.body.style.overflow = savedOverflow
    }
  })
}
