<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  collectionId: { type: Number, required: true },
  artifactType: { type: String, required: true },
  // The logical filesystem path to preview
  path: { type: String, required: true },
})
const emit = defineEmits(['close'])

// ── State ─────────────────────────────────────────────────────────────────────
const state    = ref('loading') // loading | unavailable | binary | success
const content  = ref(null)
const fileSize = ref(null)
const truncated = ref(false)
const copied   = ref(false)

// ── Fetch ──────────────────────────────────────────────────────────────────────
async function load() {
  state.value   = 'loading'
  content.value = null
  copied.value  = false
  try {
    const { data } = await axios.get(
      `/api/collections/${props.collectionId}/file-preview`,
      { params: { path: props.path } },
    )
    fileSize.value  = data.size
    truncated.value = data.truncated ?? false
    if (!data.available) {
      state.value = 'unavailable'
    } else if (data.binary) {
      state.value = 'binary'
    } else {
      content.value = data.content ?? ''
      state.value   = 'success'
    }
  } catch {
    state.value = 'unavailable'
  }
}

watch(() => props.path, load, { immediate: true })

// ── Copy to clipboard ─────────────────────────────────────────────────────────
async function copyContent() {
  if (!content.value) return
  try {
    await navigator.clipboard.writeText(content.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Clipboard not available — silently ignore
  }
}

// ── Line numbers ──────────────────────────────────────────────────────────────
const lines = computed(() => (content.value ?? '').split('\n'))

// ── Type badge colour ─────────────────────────────────────────────────────────
const TYPE_COLORS = {
  processes:  'bg-purple-900/60 text-purple-300 border-purple-700',
  auth:       'bg-green-900/60 text-green-300 border-green-700',
  cmdhistory: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  netconns:   'bg-cyan-900/60 text-cyan-300 border-cyan-700',
  files:      'bg-orange-900/60 text-orange-300 border-orange-700',
  services:   'bg-blue-900/60 text-blue-300 border-blue-700',
  cron:       'bg-pink-900/60 text-pink-300 border-pink-700',
  rcscripts:  'bg-red-900/60 text-red-300 border-red-700',
}
const typeClass = computed(
  () => TYPE_COLORS[props.artifactType] ?? 'bg-tn-raised text-tn-fg-dim border-tn-border',
)

// ── File size helper ──────────────────────────────────────────────────────────
function fmtSize(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ── Keyboard / outside-click close ───────────────────────────────────────────
function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <div
      class="fixed inset-0 z-[9990] bg-black/60 flex items-center justify-center p-6"
      @mousedown.self="emit('close')"
    >
      <!-- Modal panel -->
      <div class="flex flex-col bg-tn-surface border border-tn-border rounded-lg shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden">

        <!-- Header -->
        <div class="flex items-center gap-3 px-4 py-3 border-b border-tn-border shrink-0">
          <span :class="['text-xs font-mono px-1.5 py-0.5 rounded border shrink-0', typeClass]">
            {{ artifactType }}
          </span>
          <span class="font-mono text-xs text-tn-fg truncate flex-1" :title="path">{{ path }}</span>
          <div class="flex items-center gap-2 shrink-0">
            <!-- File size -->
            <span v-if="fileSize != null" class="text-xs text-tn-muted font-mono">
              {{ fmtSize(fileSize) }}
            </span>
            <!-- Truncated warning -->
            <span
              v-if="truncated"
              class="text-xs px-1.5 py-0.5 rounded border bg-yellow-900/60 text-yellow-300 border-yellow-700"
              title="File exceeds 512 KB preview limit — showing first 512 KB"
            >truncated</span>
            <!-- Copy button (only when content loaded) -->
            <button
              v-if="state === 'success'"
              @click="copyContent"
              :class="[
                'text-xs px-2 py-1 rounded border transition-colors',
                copied
                  ? 'bg-green-900/60 text-green-300 border-green-700'
                  : 'bg-tn-hover border-tn-border text-tn-fg-dim hover:text-tn-fg hover:border-tn-border-strong',
              ]"
            >{{ copied ? 'Copied!' : 'Copy' }}</button>
            <!-- Close -->
            <button
              @click="emit('close')"
              class="text-tn-muted hover:text-tn-fg transition-colors text-base leading-none px-1"
              title="Close (Esc)"
            >×</button>
          </div>
        </div>

        <!-- Body -->
        <div class="flex-1 overflow-auto min-h-0">

          <!-- Loading -->
          <div v-if="state === 'loading'" class="p-8 text-center text-tn-muted text-sm">
            Loading…
          </div>

          <!-- Unavailable -->
          <div v-else-if="state === 'unavailable'" class="p-8 text-center text-tn-muted text-sm">
            <div class="text-lg mb-2">File not available</div>
            <div class="font-mono text-xs text-tn-fg-dim">{{ path }}</div>
            <div class="mt-2 text-xs">This file was not captured in the collection.</div>
          </div>

          <!-- Binary -->
          <div v-else-if="state === 'binary'" class="p-8 text-center text-tn-muted text-sm">
            <div class="text-lg mb-2">Binary file</div>
            <div class="font-mono text-xs text-tn-fg-dim">{{ path }}</div>
            <div class="mt-2 text-xs">Binary files cannot be previewed.</div>
          </div>

          <!-- Success — code view with line numbers -->
          <div v-else class="flex min-h-0 font-mono text-xs">
            <!-- Line numbers -->
            <div
              class="select-none text-right text-tn-muted bg-tn-bg/60 border-r border-tn-border px-3 py-3 shrink-0"
              aria-hidden="true"
            >
              <div v-for="n in lines.length" :key="n" class="leading-5">{{ n }}</div>
            </div>
            <!-- Content -->
            <pre class="flex-1 px-4 py-3 leading-5 overflow-x-auto whitespace-pre text-tn-fg">{{ content }}</pre>
          </div>

        </div>
      </div>
    </div>
  </Teleport>
</template>
