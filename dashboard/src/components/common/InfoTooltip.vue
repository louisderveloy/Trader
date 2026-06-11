<template>
  <!-- "?" help tooltip. The popover is teleported to <body> and positioned with
       fixed viewport coordinates so it is never clipped by a modal's overflow or
       hidden behind another stacking context, and is clamped to stay on screen. -->
  <span class="inline-flex align-middle">
    <button
      ref="btn"
      type="button"
      aria-label="Aide"
      class="w-5 h-5 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-xs font-bold hover:bg-blue-300 transition-colors"
      @mouseenter="open"
      @mouseleave="close"
      @focus="open"
      @blur="close"
    >
      ?
    </button>

    <Teleport to="body">
      <div
        v-if="show"
        ref="pop"
        role="tooltip"
        class="fixed z-[9999] px-3 py-2 bg-gray-900 text-white text-xs leading-snug rounded shadow-lg whitespace-normal break-words pointer-events-none"
        :style="style"
      >
        {{ text }}
      </div>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'

defineProps<{ text: string }>()

const btn = ref<HTMLButtonElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const show = ref(false)
const style = ref<Record<string, string>>({ visibility: 'hidden', left: '0px', top: '0px' })

const MARGIN = 8
const MAX_WIDTH = 288 // ~ w-72

async function open(): Promise<void> {
  // Cap width up front so the measured rect reflects the wrapped size.
  const maxW = Math.min(MAX_WIDTH, window.innerWidth - MARGIN * 2)
  style.value = { maxWidth: `${maxW}px`, left: '0px', top: '0px', visibility: 'hidden' }
  show.value = true

  await nextTick()
  const b = btn.value?.getBoundingClientRect()
  const p = pop.value
  if (!b || !p) return

  const r = p.getBoundingClientRect()
  // Centre above the trigger, clamped to the viewport horizontally.
  let left = b.left + b.width / 2 - r.width / 2
  left = Math.max(MARGIN, Math.min(left, window.innerWidth - r.width - MARGIN))
  // Prefer above; flip below if there isn't room.
  let top = b.top - r.height - MARGIN
  if (top < MARGIN) top = b.bottom + MARGIN

  style.value = {
    maxWidth: `${maxW}px`,
    left: `${left}px`,
    top: `${top}px`,
    visibility: 'visible',
  }
}

function close(): void {
  show.value = false
}
</script>
