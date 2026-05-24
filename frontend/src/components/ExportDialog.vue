<script setup>
import { ref, computed } from 'vue'
import { useTagsStore } from '../stores/tags.js'

const props = defineProps({
  collectionId: { type: Number, required: true },
  collectionHostname: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const tagsStore = useTagsStore()

const selectedIds = ref(new Set())
const loading = ref(false)
const error = ref(null)

const canExport = computed(() => selectedIds.value.size > 0)

const TAG_CHIP_CLASSES = {
  red:    'bg-red-900/60 text-red-300 border-red-700',
  orange: 'bg-orange-900/60 text-orange-300 border-orange-700',
  yellow: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  green:  'bg-green-900/60 text-green-300 border-green-700',
  teal:   'bg-teal-900/60 text-teal-300 border-teal-700',
  blue:   'bg-blue-900/60 text-blue-300 border-blue-700',
  purple: 'bg-purple-900/60 text-purple-300 border-purple-700',
  pink:   'bg-pink-900/60 text-pink-300 border-pink-700',
  gray:   'bg-tn-hover/60 text-tn-fg-dim border-tn-border-strong',
}

function toggleTag(id) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function selectAll() {
  selectedIds.value = new Set(tagsStore.tags.map(t => t.id))
}

function clearAll() {
  selectedIds.value = new Set()
}

async function doExport() {
  if (!canExport.value) return
  loading.value = true
  error.value = null
  try {
    const tagParam = [...selectedIds.value].join(',')
    const res = await fetch(`/api/collections/${props.collectionId}/export?tag_ids=${tagParam}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Export failed (${res.status})`)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const disposition = res.headers.get('content-disposition') ?? ''
    const match = disposition.match(/filename="([^"]+)"/)
    a.download = match ? match[1] : `${props.collectionHostname || 'export'}.xlsx`
    a.href = url
    a.click()
    URL.revokeObjectURL(url)
    emit('close')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onOverlayClick(e) {
  if (e.target === e.currentTarget) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      @click="onOverlayClick"
    >
      <div class="bg-tn-surface border border-tn-border rounded-xl shadow-2xl w-full max-w-md mx-4 flex flex-col">

        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-tn-border">
          <div>
            <div class="font-semibold text-tn-fg">Export to Excel</div>
            <div class="text-xs text-tn-muted mt-0.5">
              Rows matching any selected tag will be exported.
            </div>
          </div>
          <button
            @click="emit('close')"
            class="text-tn-fg-dim hover:text-tn-fg transition-colors p-1 rounded"
          >✕</button>
        </div>

        <!-- Tag selection -->
        <div class="px-5 py-4 flex-1 overflow-y-auto">
          <div v-if="tagsStore.tags.length === 0" class="text-sm text-tn-muted italic">
            No tags defined. Tag some rows first.
          </div>

          <template v-else>
            <div class="flex items-center justify-between mb-3">
              <span class="text-xs text-tn-fg-dim">Select tags to include</span>
              <div class="flex gap-2">
                <button @click="selectAll" class="text-xs text-tn-accent hover:text-tn-accent-hover transition-colors">All</button>
                <span class="text-tn-border">|</span>
                <button @click="clearAll" class="text-xs text-tn-fg-dim hover:text-tn-fg transition-colors">None</button>
              </div>
            </div>

            <div class="flex flex-col gap-1.5">
              <label
                v-for="tag in tagsStore.tags"
                :key="tag.id"
                class="flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition-colors"
                :class="selectedIds.has(tag.id) ? 'bg-tn-selection' : 'hover:bg-tn-raised/60'"
              >
                <input
                  type="checkbox"
                  :checked="selectedIds.has(tag.id)"
                  @change="toggleTag(tag.id)"
                  class="accent-tn-accent"
                />
                <span
                  :class="['inline-flex items-center text-xs font-mono px-2 py-0.5 rounded border',
                    TAG_CHIP_CLASSES[tag.color] ?? TAG_CHIP_CLASSES.gray]"
                >{{ tag.name }}</span>
              </label>
            </div>
          </template>
        </div>

        <!-- Error -->
        <div v-if="error" class="mx-5 mb-3 px-3 py-2 rounded bg-red-950/40 border border-red-800 text-xs text-red-300">
          {{ error }}
        </div>

        <!-- Footer -->
        <div class="flex gap-2 px-5 py-4 border-t border-tn-border">
          <button
            @click="doExport"
            :disabled="!canExport || loading"
            class="flex-1 px-4 py-2 rounded bg-tn-accent hover:bg-tn-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-tn-bg text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            <span v-if="loading" class="animate-spin text-base leading-none">↻</span>
            {{ loading ? 'Exporting…' : 'Export' }}
          </button>
          <button
            @click="emit('close')"
            class="px-4 py-2 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim text-sm transition-colors"
          >Cancel</button>
        </div>

      </div>
    </div>
  </Teleport>
</template>
