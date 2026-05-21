<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'

const props = defineProps({
  items: {
    // Array of { label: string, disabled?: bool, separator?: bool }
    type: Array,
    required: true,
  },
  x: { type: Number, required: true },
  y: { type: Number, required: true },
})
const emit = defineEmits(['select', 'close'])

const el = ref(null)

// Flip position so the menu stays within the viewport
const style = computed(() => {
  const vw = window.innerWidth
  const vh = window.innerHeight
  // Estimated menu dimensions before render; refined after mount via nextTick
  const estW = 180
  const estH = props.items.length * 32
  const left = props.x + estW > vw ? props.x - estW : props.x
  const top  = props.y + estH > vh ? props.y - estH : props.y
  return { left: `${Math.max(4, left)}px`, top: `${Math.max(4, top)}px` }
})

function select(item, idx) {
  if (item.separator || item.disabled) return
  emit('select', idx)
  emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

function onMousedown(e) {
  if (el.value && !el.value.contains(e.target)) emit('close')
}

onMounted(() => {
  document.addEventListener('mousedown', onMousedown)
  document.addEventListener('keydown', onKeydown)
  // Refine position after the element is rendered
  nextTick(() => {
    if (!el.value) return
    const rect = el.value.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    if (rect.right > vw) el.value.style.left = `${Math.max(4, props.x - rect.width)}px`
    if (rect.bottom > vh) el.value.style.top  = `${Math.max(4, props.y - rect.height)}px`
  })
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onMousedown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div
      ref="el"
      :style="style"
      class="fixed z-[9999] min-w-44 bg-tn-surface border border-tn-border rounded shadow-xl text-xs py-1 select-none"
      @click.stop
      @contextmenu.prevent
    >
      <template v-for="(item, idx) in items" :key="idx">
        <div v-if="item.separator" class="my-1 border-t border-tn-border" />
        <button
          v-else
          :disabled="item.disabled"
          @click="select(item, idx)"
          :class="[
            'w-full text-left px-3 py-1.5 flex items-center gap-2',
            item.disabled
              ? 'text-tn-muted cursor-default'
              : 'text-tn-fg hover:bg-tn-raised cursor-pointer',
          ]"
        >
          {{ item.label }}
        </button>
      </template>
    </div>
  </Teleport>
</template>
