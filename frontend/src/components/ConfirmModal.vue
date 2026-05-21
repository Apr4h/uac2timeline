<script setup>
import { onMounted, onUnmounted } from 'vue'

const props = defineProps({
  message:      { type: String, required: true },
  confirmLabel: { type: String, default: 'Confirm' },
  destructive:  { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'close'])

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
  if (e.key === 'Enter')  emit('confirm')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[9995] bg-black/60 flex items-center justify-center p-6"
      @mousedown.self="emit('close')"
    >
      <div class="bg-tn-surface border border-tn-border rounded-lg shadow-2xl w-full max-w-sm p-5 flex flex-col gap-4">
        <p class="text-sm text-tn-fg">{{ message }}</p>
        <div class="flex gap-2 justify-end">
          <button
            @click="emit('close')"
            class="px-3 py-1.5 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim text-sm"
          >Cancel</button>
          <button
            @click="emit('confirm')"
            :class="[
              'px-3 py-1.5 rounded text-sm transition-colors',
              destructive
                ? 'bg-red-700 hover:bg-red-600 text-white'
                : 'bg-tn-accent hover:bg-tn-accent-hover text-tn-bg',
            ]"
          >{{ confirmLabel }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
