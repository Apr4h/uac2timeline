<script setup>
import { ref, computed } from 'vue'
import { useTagsStore } from '../stores/tags.js'
import TagBadge from './TagBadge.vue'
import TagPicker from './TagPicker.vue'

const props = defineProps({
  events: Array,
  total: Number,
  loading: Boolean,
})
const emit = defineEmits(['loadMore'])

const tagsStore = useTagsStore()

// ── Row expansion ─────────────────────────────────────────────────────────────
const expanded = ref(new Set())

function toggleRow(key) {
  if (expanded.value.has(key)) expanded.value.delete(key)
  else expanded.value.add(key)
  expanded.value = new Set(expanded.value)
}

// ── Row selection ─────────────────────────────────────────────────────────────
const selected = ref(new Set())   // Set of row keys
const lastClickedKey = ref(null)  // anchor for shift-click range selection
let _shiftCapture = false         // bridges mousedown → change; not reactive

function captureShift(event) { _shiftCapture = event.shiftKey }

function rowKey(ev) {
  return `${ev.artifact_type}-${ev.id}-${ev.timestamp}`
}

function toggleSelect(ev) {
  const k = rowKey(ev)
  const wasShift = _shiftCapture
  _shiftCapture = false

  if (wasShift && lastClickedKey.value !== null) {
    const keys = (props.events ?? []).map(rowKey)
    const anchorIdx = keys.indexOf(lastClickedKey.value)
    const targetIdx = keys.indexOf(k)
    if (anchorIdx !== -1 && targetIdx !== -1) {
      const [lo, hi] = anchorIdx < targetIdx ? [anchorIdx, targetIdx] : [targetIdx, anchorIdx]
      const next = new Set(selected.value)
      for (let i = lo; i <= hi; i++) next.add(keys[i])
      selected.value = next
      return
    }
  }
  const next = new Set(selected.value)
  if (next.has(k)) next.delete(k)
  else next.add(k)
  selected.value = next
  lastClickedKey.value = k
}

const allSelected = computed(
  () => props.events?.length > 0 && props.events.every(ev => selected.value.has(rowKey(ev)))
)

function toggleSelectAll() {
  lastClickedKey.value = null
  if (allSelected.value) {
    selected.value = new Set()
  } else {
    selected.value = new Set(props.events.map(rowKey))
  }
}

const selectedEvents = computed(() =>
  (props.events ?? []).filter(ev => selected.value.has(rowKey(ev)))
)

function clearSelection() { selected.value = new Set() }

// ── Tag picker ────────────────────────────────────────────────────────────────
// activePickerKey: row key for per-row picker; 'bulk' for bulk picker
const activePickerKey = ref(null)

function openPicker(key, event) {
  event?.stopPropagation()
  activePickerKey.value = activePickerKey.value === key ? null : key
}

function closePicker() { activePickerKey.value = null }

// Applied/partial sets for whichever picker is open
const pickerApplied = computed(() => {
  if (!activePickerKey.value) return new Set()
  if (activePickerKey.value === 'bulk') {
    return tagsStore.getBulkTagState(selectedEvents.value.map(ev => ({
      artifactType: ev.artifact_type, artifactId: ev.id,
    }))).applied
  }
  // per-row
  const ev = (props.events ?? []).find(e => rowKey(e) === activePickerKey.value)
  if (!ev) return new Set()
  return new Set(tagsStore.getRowTags(ev.artifact_type, ev.id).map(t => t.id))
})

const pickerPartial = computed(() => {
  if (activePickerKey.value !== 'bulk') return new Set()
  return tagsStore.getBulkTagState(selectedEvents.value.map(ev => ({
    artifactType: ev.artifact_type, artifactId: ev.id,
  }))).partial
})

async function onPickerApply(tagId) {
  if (activePickerKey.value === 'bulk') {
    const grouped = groupSelectedByType(selectedEvents.value)
    for (const [type, ids] of Object.entries(grouped)) {
      await tagsStore.applyTag(tagId, type, ids)
    }
  } else {
    const ev = (props.events ?? []).find(e => rowKey(e) === activePickerKey.value)
    if (ev) await tagsStore.applyTag(tagId, ev.artifact_type, [ev.id])
  }
}

async function onPickerRemove(tagId) {
  if (activePickerKey.value === 'bulk') {
    const grouped = groupSelectedByType(selectedEvents.value)
    for (const [type, ids] of Object.entries(grouped)) {
      await tagsStore.removeTag(tagId, type, ids)
    }
  } else {
    const ev = (props.events ?? []).find(e => rowKey(e) === activePickerKey.value)
    if (ev) await tagsStore.removeTag(tagId, ev.artifact_type, [ev.id])
  }
}

function groupSelectedByType(events) {
  const groups = {}
  for (const ev of events) {
    if (!groups[ev.artifact_type]) groups[ev.artifact_type] = new Set()
    groups[ev.artifact_type].add(ev.id)
  }
  return Object.fromEntries(
    Object.entries(groups).map(([type, ids]) => [type, [...ids]])
  )
}

async function removeTagFromRow(ev, tag) {
  await tagsStore.removeTag(tag.id, ev.artifact_type, [ev.id])
}

// ── Type badge colors ─────────────────────────────────────────────────────────
const TYPE_COLORS = {
  processes:  'bg-purple-900/60 text-purple-300 border-purple-700',
  auth:       'bg-green-900/60 text-green-300 border-green-700',
  cmdhistory: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  netconns:   'bg-cyan-900/60 text-cyan-300 border-cyan-700',
  files:      'bg-orange-900/60 text-orange-300 border-orange-700',
}

function typeClass(t) {
  return TYPE_COLORS[t] || 'bg-gray-800 text-gray-300 border-gray-600'
}

function fmtTs(ts) {
  if (!ts) return '—'
  return new Date(ts).toISOString().replace('T', ' ').replace('Z', '').slice(0, 19)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="overflow-auto flex-1">
      <table class="w-full text-sm border-collapse">
        <thead class="sticky top-0 bg-gray-900 border-b border-gray-700 z-10">
          <tr>
            <!-- Select-all checkbox -->
            <th class="w-8 px-2 py-2">
              <input
                type="checkbox"
                :checked="allSelected"
                :indeterminate="selected.size > 0 && !allSelected"
                @change="toggleSelectAll"
                class="accent-blue-500 cursor-pointer"
              />
            </th>
            <th class="text-left px-3 py-2 text-xs text-gray-400 font-medium w-44">Timestamp</th>
            <th class="text-left px-3 py-2 text-xs text-gray-400 font-medium w-28">Type</th>
            <th class="text-left px-3 py-2 text-xs text-gray-400 font-medium">Summary</th>
            <th class="text-left px-3 py-2 text-xs text-gray-400 font-medium w-48">Tags</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr>
              <td colspan="5" class="px-3 py-8 text-center text-gray-500">Loading…</td>
            </tr>
          </template>
          <template v-else-if="!events?.length">
            <tr>
              <td colspan="5" class="px-3 py-8 text-center text-gray-500">No events match the current filters.</td>
            </tr>
          </template>
          <template v-else v-for="ev in events" :key="rowKey(ev)">
            <tr
              :class="[
                'border-b border-gray-800 cursor-pointer',
                selected.has(rowKey(ev)) ? 'bg-blue-950/40 hover:bg-blue-950/60' : 'hover:bg-gray-800/50',
              ]"
              @click="toggleRow(rowKey(ev))"
            >
              <!-- Checkbox -->
              <td class="w-8 px-2 py-1.5" @click.stop>
                <input
                  type="checkbox"
                  :checked="selected.has(rowKey(ev))"
                  @mousedown="captureShift"
                  @change="toggleSelect(ev)"
                  class="accent-blue-500 cursor-pointer"
                />
              </td>
              <td class="px-3 py-1.5 font-mono text-xs text-gray-400 whitespace-nowrap">{{ fmtTs(ev.timestamp) }}</td>
              <td class="px-3 py-1.5">
                <span :class="['text-xs font-mono px-1.5 py-0.5 rounded border', typeClass(ev.artifact_type)]">
                  {{ ev.artifact_type }}
                </span>
              </td>
              <td class="px-3 py-1.5 text-gray-200 font-mono text-xs truncate max-w-0 w-full">{{ ev.summary }}</td>
              <!-- Tags cell -->
              <td class="px-3 py-1.5 relative" @click.stop>
                <div class="flex items-center gap-1 flex-wrap">
                  <TagBadge
                    v-for="tag in tagsStore.getRowTags(ev.artifact_type, ev.id)"
                    :key="tag.id"
                    :tag="tag"
                    removable
                    @remove="removeTagFromRow(ev, tag)"
                  />
                  <button
                    @click="openPicker(rowKey(ev), $event)"
                    class="text-gray-500 hover:text-gray-300 text-xs px-1 rounded hover:bg-gray-700"
                    title="Add tag"
                  >+</button>
                  <TagPicker
                    v-if="activePickerKey === rowKey(ev)"
                    :applied-ids="pickerApplied"
                    :partial-ids="pickerPartial"
                    @apply="onPickerApply"
                    @remove="onPickerRemove"
                    @create="closePicker"
                    @close="closePicker"
                  />
                </div>
              </td>
            </tr>

            <!-- Expanded details row -->
            <tr v-if="expanded.has(rowKey(ev))" class="border-b border-gray-800 bg-gray-950/60">
              <td colspan="5" class="px-4 py-3">
                <div class="grid grid-cols-2 gap-x-6 gap-y-1">
                  <template v-for="(val, key) in ev.details" :key="key">
                    <template v-if="val !== null && val !== undefined && val !== ''">
                      <div class="text-xs text-gray-400 font-mono">{{ key }}</div>
                      <div class="text-xs text-gray-200 font-mono break-all">{{ val }}</div>
                    </template>
                  </template>
                </div>
                <!-- Tags section -->
                <div class="mt-3 pt-2 border-t border-gray-700 flex items-center gap-2 flex-wrap">
                  <span class="text-xs text-gray-500 font-mono">tags:</span>
                  <TagBadge
                    v-for="tag in tagsStore.getRowTags(ev.artifact_type, ev.id)"
                    :key="tag.id"
                    :tag="tag"
                    removable
                    @remove="removeTagFromRow(ev, tag)"
                  />
                  <div class="relative">
                    <button
                      @click="openPicker(`detail-${rowKey(ev)}`, $event)"
                      class="text-xs text-blue-400 hover:text-blue-300 border border-blue-700 hover:border-blue-500 rounded px-1.5 py-0.5"
                    >+ Tag</button>
                    <TagPicker
                      v-if="activePickerKey === `detail-${rowKey(ev)}`"
                      :applied-ids="new Set(tagsStore.getRowTags(ev.artifact_type, ev.id).map(t => t.id))"
                      :partial-ids="new Set()"
                      @apply="id => tagsStore.applyTag(id, ev.artifact_type, [ev.id])"
                      @remove="id => tagsStore.removeTag(id, ev.artifact_type, [ev.id])"
                      @close="closePicker"
                    />
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Footer: count + load more -->
    <div class="border-t border-gray-700 px-4 py-2 flex items-center justify-between text-xs text-gray-400">
      <span>Showing {{ events?.length ?? 0 }} of {{ total ?? 0 }} events</span>
      <button
        v-if="events?.length < total"
        @click="emit('loadMore')"
        class="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
      >
        Load more
      </button>
    </div>

    <!-- Bulk action bar -->
    <Transition name="slide-up">
      <div
        v-if="selected.size > 0"
        class="border-t border-blue-700 bg-blue-950/80 px-4 py-2 flex items-center gap-3 text-xs"
      >
        <span class="text-blue-300 font-mono">{{ selected.size }} row{{ selected.size === 1 ? '' : 's' }} selected</span>
        <div class="relative">
          <button
            @click="openPicker('bulk', $event)"
            class="px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 text-white"
          >Tag selected</button>
          <TagPicker
            v-if="activePickerKey === 'bulk'"
            :applied-ids="pickerApplied"
            :partial-ids="pickerPartial"
            @apply="onPickerApply"
            @remove="onPickerRemove"
            @close="closePicker"
            class="-top-2 -translate-y-full"
          />
        </div>
        <button
          @click="clearSelection"
          class="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
        >Clear</button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
