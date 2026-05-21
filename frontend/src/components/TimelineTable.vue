<script setup>
import { ref, computed } from 'vue'
import { useTagsStore } from '../stores/tags.js'
import { useNotesStore } from '../stores/notes.js'
import TagBadge from './TagBadge.vue'
import TagPicker from './TagPicker.vue'
import ContextMenu from './ContextMenu.vue'
import FilePreviewModal from './FilePreviewModal.vue'
import NoteModal from './NoteModal.vue'
import ConfirmModal from './ConfirmModal.vue'

const props = defineProps({
  events: Array,
  total: Number,
  loading: Boolean,
  collectionId: Number,
})
const emit = defineEmits(['loadMore'])

const tagsStore = useTagsStore()
const notesStore = useNotesStore()

// ── Row expansion ─────────────────────────────────────────────────────────────
const expanded = ref(new Set())

function toggleRow(key) {
  if (expanded.value.has(key)) expanded.value.delete(key)
  else expanded.value.add(key)
  expanded.value = new Set(expanded.value)
}

// ── Row selection ─────────────────────────────────────────────────────────────
const selected = ref(new Set())
const lastClickedKey = ref(null)
let _shiftCapture = false

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
const activePickerKey  = ref(null)
const activePickerRect = ref(null)

function openPicker(key, event) {
  event?.stopPropagation()
  if (activePickerKey.value === key) {
    activePickerKey.value  = null
    activePickerRect.value = null
  } else {
    activePickerKey.value  = key
    activePickerRect.value = event?.currentTarget?.getBoundingClientRect() ?? null
  }
}

function closePicker() {
  activePickerKey.value  = null
  activePickerRect.value = null
}

const pickerApplied = computed(() => {
  if (!activePickerKey.value) return new Set()
  if (activePickerKey.value === 'bulk') {
    return tagsStore.getBulkTagState(selectedEvents.value.map(ev => ({
      artifactType: ev.artifact_type, artifactId: ev.id,
    }))).applied
  }
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
  services:   'bg-blue-900/60 text-blue-300 border-blue-700',
  cron:       'bg-pink-900/60 text-pink-300 border-pink-700',
  rcscripts:  'bg-red-900/60 text-red-300 border-red-700',
}

function typeClass(t) {
  return TYPE_COLORS[t] || 'bg-tn-raised text-tn-fg-dim border-tn-border'
}

function fmtTs(ts) {
  if (!ts) return '—'
  return new Date(ts).toISOString().replace('T', ' ').replace('Z', '').slice(0, 19)
}

// ── File preview ──────────────────────────────────────────────────────────────
// Maps artifact_type → the details key that holds the logical filesystem path
const FILE_PREVIEW_FIELD = {
  rcscripts:  'path',
  cron:       'source_file',
  services:   'source_path',
  files:      'path',
  cmdhistory: 'history_file',
}

function getPreviewPath(ev) {
  const field = FILE_PREVIEW_FIELD[ev.artifact_type]
  return field ? (ev.details?.[field] ?? null) : null
}

const contextMenu    = ref(null)  // { x, y, items } | null
const previewTarget  = ref(null)  // { artifactType, path } | null
const noteModalTarget  = ref(null)  // { isBulk, rows?, ev?, initialContent, notesDiffer }
const confirmTarget  = ref(null)  // { message, rows?, ev? }

function openContextMenu(ev, mouseEvent) {
  const previewPath = getPreviewPath(ev)
  const isBulkCtx = selected.value.has(rowKey(ev)) && selected.value.size > 1

  // ── Note items ──────────────────────────────────────────────────────────────
  const noteItems = []
  if (isBulkCtx) {
    const rows = (props.events ?? [])
      .filter(e => selected.value.has(rowKey(e)))
      .map(e => ({ artifactType: e.artifact_type, artifactId: e.id }))
    const n = rows.length
    const state = notesStore.getBulkNoteState(rows)
    const label = (state.hasAny && !state.allSameContent)
      ? `Edit note for ${n} row${n === 1 ? '' : 's'}`
      : state.hasAny
        ? `Edit note for ${n} row${n === 1 ? '' : 's'}`
        : `Add note to ${n} row${n === 1 ? '' : 's'}`
    noteItems.push({ label, _action: 'note-edit', _isBulk: true, _rows: rows, _state: state })
    if (state.hasAny) {
      noteItems.push({ separator: true })
      noteItems.push({
        label: `Delete note from ${state.noteCount} row${state.noteCount === 1 ? '' : 's'}`,
        _action: 'note-delete', _isBulk: true, _rows: rows, _state: state,
      })
    }
  } else {
    const note = notesStore.getNoteForRow(ev.artifact_type, ev.id)
    noteItems.push({
      label: note ? 'Edit note' : 'Add note',
      _action: 'note-edit', _isBulk: false, _ev: ev, _note: note,
    })
    if (note) {
      noteItems.push({ separator: true })
      noteItems.push({ label: 'Delete note', _action: 'note-delete', _isBulk: false, _ev: ev })
    }
  }

  contextMenu.value = {
    x: mouseEvent.clientX,
    y: mouseEvent.clientY,
    items: [
      { label: 'Open file preview', disabled: !previewPath, _action: 'preview', _path: previewPath, _type: ev.artifact_type },
      { separator: true },
      ...noteItems,
    ],
  }
}

function onContextMenuSelect(idx) {
  const item = contextMenu.value?.items[idx]
  contextMenu.value = null
  if (!item || item.disabled || item.separator) return

  if (item._action === 'preview') {
    previewTarget.value = { artifactType: item._type, path: item._path }
    return
  }

  if (item._action === 'note-edit') {
    if (item._isBulk) {
      const s = item._state
      noteModalTarget.value = {
        isBulk: true,
        rows: item._rows,
        initialContent: s.allSameContent ? s.commonContent : '',
        notesDiffer: s.hasAny && !s.allSameContent,
      }
    } else {
      noteModalTarget.value = {
        isBulk: false,
        ev: item._ev,
        initialContent: item._note?.content ?? '',
        notesDiffer: false,
      }
    }
    return
  }

  if (item._action === 'note-delete') {
    if (item._isBulk) {
      const n = item._state.noteCount
      confirmTarget.value = {
        message: `Delete note from ${n} row${n === 1 ? '' : 's'}?`,
        isBulk: true,
        rows: item._rows,
      }
    } else {
      confirmTarget.value = {
        message: 'Delete this note?',
        isBulk: false,
        ev: item._ev,
      }
    }
  }
}

async function onNoteSave(content) {
  const t = noteModalTarget.value
  noteModalTarget.value = null
  if (!t || !props.collectionId) return
  if (t.isBulk) {
    const grouped = {}
    for (const r of t.rows) {
      if (!grouped[r.artifactType]) grouped[r.artifactType] = []
      grouped[r.artifactType].push(r.artifactId)
    }
    for (const [type, ids] of Object.entries(grouped)) {
      await notesStore.upsertNote(type, ids, props.collectionId, content)
    }
  } else {
    await notesStore.upsertNote(t.ev.artifact_type, [t.ev.id], props.collectionId, content)
  }
}

async function onNoteDeleteConfirm() {
  const t = confirmTarget.value
  confirmTarget.value = null
  if (!t) return
  if (t.isBulk) {
    const grouped = {}
    for (const r of t.rows) {
      const note = notesStore.getNoteForRow(r.artifactType, r.artifactId)
      if (note) {
        if (!grouped[r.artifactType]) grouped[r.artifactType] = []
        grouped[r.artifactType].push(r.artifactId)
      }
    }
    for (const [type, ids] of Object.entries(grouped)) {
      await notesStore.deleteNote(type, ids)
    }
  } else {
    await notesStore.deleteNote(t.ev.artifact_type, [t.ev.id])
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="overflow-auto flex-1">
      <table class="w-full text-sm border-collapse">
        <thead class="sticky top-0 bg-tn-surface border-b border-tn-border z-10">
          <tr>
            <th class="w-8 px-2 py-2">
              <input
                type="checkbox"
                :checked="allSelected"
                :indeterminate="selected.size > 0 && !allSelected"
                @change="toggleSelectAll"
                class="accent-tn-accent cursor-pointer"
              />
            </th>
            <th class="text-left px-3 py-2 text-xs text-tn-fg-dim font-medium w-44">Timestamp</th>
            <th class="text-left px-3 py-2 text-xs text-tn-fg-dim font-medium w-28">Type</th>
            <th class="text-left px-3 py-2 text-xs text-tn-fg-dim font-medium">Summary</th>
            <th class="text-left px-3 py-2 text-xs text-tn-fg-dim font-medium w-48">Note</th>
            <th class="text-left px-3 py-2 text-xs text-tn-fg-dim font-medium w-48">Tags</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr>
              <td colspan="6" class="px-3 py-8 text-center text-tn-muted">Loading…</td>
            </tr>
          </template>
          <template v-else-if="!events?.length">
            <tr>
              <td colspan="6" class="px-3 py-8 text-center text-tn-muted">No events match the current filters.</td>
            </tr>
          </template>
          <template v-else v-for="ev in events" :key="rowKey(ev)">
            <tr
              :class="[
                'border-b border-tn-border cursor-pointer',
                selected.has(rowKey(ev)) ? 'bg-tn-selection hover:bg-tn-selection-hover' : 'hover:bg-tn-raised/50',
              ]"
              @click="toggleRow(rowKey(ev))"
              @contextmenu.prevent="openContextMenu(ev, $event)"
            >
              <td class="w-8 px-2 py-1.5" @click.stop>
                <input
                  type="checkbox"
                  :checked="selected.has(rowKey(ev))"
                  @mousedown="captureShift"
                  @change="toggleSelect(ev)"
                  class="accent-tn-accent cursor-pointer"
                />
              </td>
              <td class="px-3 py-1.5 font-mono text-xs text-tn-fg-dim whitespace-nowrap">{{ fmtTs(ev.timestamp) }}</td>
              <td class="px-3 py-1.5">
                <span :class="['text-xs font-mono px-1.5 py-0.5 rounded border', typeClass(ev.artifact_type)]">
                  {{ ev.artifact_type }}
                </span>
              </td>
              <td class="px-3 py-1.5 text-tn-fg font-mono text-xs truncate max-w-0 w-full">{{ ev.summary }}</td>
              <td class="px-3 py-1.5 w-48 max-w-48" @click.stop>
                <span
                  v-if="notesStore.getNoteForRow(ev.artifact_type, ev.id)"
                  class="text-xs text-tn-fg-dim font-mono truncate block max-w-full cursor-default"
                  :title="notesStore.getNoteForRow(ev.artifact_type, ev.id)?.content"
                >{{ notesStore.getNoteForRow(ev.artifact_type, ev.id)?.content }}</span>
              </td>
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
                    class="text-tn-muted hover:text-tn-fg-dim text-xs px-1 rounded hover:bg-tn-hover"
                    title="Add tag"
                  >+</button>
                  <TagPicker
                    v-if="activePickerKey === rowKey(ev)"
                    :applied-ids="pickerApplied"
                    :partial-ids="pickerPartial"
                    :anchor-rect="activePickerRect"
                    @apply="onPickerApply"
                    @remove="onPickerRemove"
                    @create="closePicker"
                    @close="closePicker"
                  />
                </div>
              </td>
            </tr>

            <!-- Expanded details row -->
            <tr v-if="expanded.has(rowKey(ev))" class="border-b border-tn-border bg-tn-bg/60">
              <td colspan="6" class="px-4 py-3">
                <div class="grid grid-cols-2 gap-x-6 gap-y-1">
                  <template v-for="(val, key) in ev.details" :key="key">
                    <template v-if="val !== null && val !== undefined && val !== ''">
                      <div class="text-xs text-tn-fg-dim font-mono">{{ key }}</div>
                      <div class="text-xs text-tn-fg font-mono break-all">{{ val }}</div>
                    </template>
                  </template>
                </div>
                <div
                  v-if="notesStore.getNoteForRow(ev.artifact_type, ev.id)"
                  class="mt-3 pt-2 border-t border-tn-border flex items-start gap-2"
                >
                  <span class="text-xs text-tn-muted font-mono shrink-0">note:</span>
                  <span class="text-xs text-tn-fg font-mono break-all">{{ notesStore.getNoteForRow(ev.artifact_type, ev.id)?.content }}</span>
                </div>
                <div class="mt-3 pt-2 border-t border-tn-border flex items-center gap-2 flex-wrap">
                  <span class="text-xs text-tn-muted font-mono">tags:</span>
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
                      class="text-xs text-tn-accent hover:text-tn-accent-hover border border-tn-accent hover:border-tn-accent-hover rounded px-1.5 py-0.5"
                    >+ Tag</button>
                    <TagPicker
                      v-if="activePickerKey === `detail-${rowKey(ev)}`"
                      :applied-ids="new Set(tagsStore.getRowTags(ev.artifact_type, ev.id).map(t => t.id))"
                      :partial-ids="new Set()"
                      :anchor-rect="activePickerRect"
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

    <div class="border-t border-tn-border px-4 py-2 flex items-center justify-between text-xs text-tn-fg-dim">
      <span>Showing {{ events?.length ?? 0 }} of {{ total ?? 0 }} events</span>
      <button
        v-if="events?.length < total"
        @click="emit('loadMore')"
        class="px-3 py-1 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim"
      >
        Load more
      </button>
    </div>

    <!-- Context menu -->
    <ContextMenu
      v-if="contextMenu"
      :items="contextMenu.items"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @select="onContextMenuSelect"
      @close="contextMenu = null"
    />

    <!-- File preview modal -->
    <FilePreviewModal
      v-if="previewTarget && collectionId"
      :collection-id="collectionId"
      :artifact-type="previewTarget.artifactType"
      :path="previewTarget.path"
      @close="previewTarget = null"
    />

    <!-- Note modal -->
    <NoteModal
      v-if="noteModalTarget"
      :initial-content="noteModalTarget.initialContent"
      :is-bulk="noteModalTarget.isBulk"
      :row-count="noteModalTarget.isBulk ? noteModalTarget.rows.length : 1"
      :notes-differ="noteModalTarget.notesDiffer"
      @save="onNoteSave"
      @close="noteModalTarget = null"
    />

    <!-- Confirm delete modal -->
    <ConfirmModal
      v-if="confirmTarget"
      :message="confirmTarget.message"
      confirm-label="Delete"
      :destructive="true"
      @confirm="onNoteDeleteConfirm"
      @close="confirmTarget = null"
    />

    <!-- Bulk action bar -->
    <Transition name="slide-up">
      <div
        v-if="selected.size > 0"
        class="border-t border-tn-accent bg-tn-selection-bar px-4 py-2 flex items-center gap-3 text-xs"
      >
        <span class="text-tn-accent font-mono">{{ selected.size }} row{{ selected.size === 1 ? '' : 's' }} selected</span>
        <div class="relative">
          <button
            @click="openPicker('bulk', $event)"
            class="px-3 py-1 rounded bg-tn-accent hover:bg-tn-accent-hover text-tn-bg"
          >Tag selected</button>
          <TagPicker
            v-if="activePickerKey === 'bulk'"
            :applied-ids="pickerApplied"
            :partial-ids="pickerPartial"
            :anchor-rect="activePickerRect"
            @apply="onPickerApply"
            @remove="onPickerRemove"
            @close="closePicker"
          />
        </div>
        <button
          @click="clearSelection"
          class="px-3 py-1 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim"
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
