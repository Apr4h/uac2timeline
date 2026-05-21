<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  initialContent: { type: String, default: '' },
  isBulk:         { type: Boolean, default: false },
  rowCount:       { type: Number, default: 1 },
  notesDiffer:    { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'close'])

const MAX = 500
const text = ref(props.initialContent)

const title = computed(() => {
  if (props.isBulk) {
    const n = props.rowCount
    return props.initialContent || props.notesDiffer
      ? `Edit note for ${n} row${n === 1 ? '' : 's'}`
      : `Add note to ${n} row${n === 1 ? '' : 's'}`
  }
  return props.initialContent ? 'Edit note' : 'Add note'
})

const placeholder = computed(() =>
  props.notesDiffer
    ? 'Notes differ — entering text will overwrite all selected rows'
    : 'Enter note…'
)

const remaining = computed(() => MAX - text.value.length)

const counterClass = computed(() => {
  if (remaining.value <= 10)  return 'text-red-400'
  if (remaining.value <= 50)  return 'text-yellow-400'
  return 'text-tn-muted'
})

const canSave = computed(() => {
  const trimmed = text.value.trim()
  return trimmed.length > 0 && trimmed !== props.initialContent.trim()
})

function save() {
  if (!canSave.value) return
  emit('save', text.value.trim())
}

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) save()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[9990] bg-black/60 flex items-center justify-center p-6"
      @mousedown.self="emit('close')"
    >
      <div class="flex flex-col bg-tn-surface border border-tn-border rounded-lg shadow-2xl w-full max-w-md">

        <!-- Header -->
        <div class="px-4 py-3 border-b border-tn-border flex items-center justify-between">
          <span class="text-sm font-medium text-tn-fg">{{ title }}</span>
          <button
            @click="emit('close')"
            class="text-tn-muted hover:text-tn-fg transition-colors text-base leading-none px-1"
            title="Close (Esc)"
          >×</button>
        </div>

        <!-- Body -->
        <div class="p-4 flex flex-col gap-2">
          <textarea
            v-model="text"
            :maxlength="MAX"
            :placeholder="placeholder"
            rows="5"
            autofocus
            class="w-full bg-tn-raised border border-tn-border-strong rounded px-3 py-2 text-sm text-tn-fg placeholder-tn-muted resize-none outline-none focus:border-tn-accent font-mono"
          />
          <div class="flex items-center justify-between text-xs">
            <span class="text-tn-muted">Ctrl+Enter to save</span>
            <span :class="counterClass">{{ text.length }} / {{ MAX }}</span>
          </div>
        </div>

        <!-- Footer -->
        <div class="px-4 pb-4 flex gap-2 justify-end">
          <button
            @click="emit('close')"
            class="px-3 py-1.5 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim text-sm"
          >Cancel</button>
          <button
            @click="save"
            :disabled="!canSave"
            :class="[
              'px-3 py-1.5 rounded text-sm transition-colors',
              canSave
                ? 'bg-tn-accent hover:bg-tn-accent-hover text-tn-bg'
                : 'bg-tn-raised text-tn-muted cursor-default',
            ]"
          >Save</button>
        </div>

      </div>
    </div>
  </Teleport>
</template>
