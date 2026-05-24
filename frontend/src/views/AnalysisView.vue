<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useTimelineStore } from '../stores/timeline.js'
import { useCollectionsStore } from '../stores/collections.js'
import { useTagsStore } from '../stores/tags.js'
import { useNotesStore } from '../stores/notes.js'
import { useColumnPrefs } from '../composables/useColumnPrefs.js'
import TimelineTable from '../components/TimelineTable.vue'
import FilterBar from '../components/FilterBar.vue'
import ProcessingStatus from '../components/ProcessingStatus.vue'
import TagBadge from '../components/TagBadge.vue'
import TagPicker from '../components/TagPicker.vue'
import ContextMenu from '../components/ContextMenu.vue'
import FilePreviewModal from '../components/FilePreviewModal.vue'
import NoteModal from '../components/NoteModal.vue'
import ConfirmModal from '../components/ConfirmModal.vue'

const route = useRoute()
const router = useRouter()
const timelineStore = useTimelineStore()
const collectionsStore = useCollectionsStore()
const tagsStore = useTagsStore()
const notesStore = useNotesStore()

const collectionId = computed(() => Number(route.params.id))
const collection = ref(null)
const activeTab = ref('timeline')
const sidebarCollapsed = ref(false)

const TABS = [
  { key: 'timeline',   label: 'Timeline' },
  { key: 'system',     label: 'System' },
  { key: 'processes',  label: 'Processes' },
  { key: 'netconns',   label: 'Network' },
  { key: 'auth',       label: 'Auth' },
  { key: 'cmdhistory', label: 'Commands' },
  { key: 'users',      label: 'Users' },
  { key: 'files',      label: 'Files' },
  { key: 'cron',       label: 'Cron' },
  { key: 'services',  label: 'Services' },
  { key: 'rcscripts', label: 'RC Scripts' },
  { key: 'syslog',    label: 'Syslog' },
]

// System info tab state
const systemInfo = ref(null)

// Per-artifact tab state
const tabData = ref({ items: [], total: 0 })
const tabLoading = ref(false)
const artifactLoadingMore = ref(false)

// Row expansion (Option A)
const expanded = ref(new Set())

function toggleExpand(id) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

// Cell value popover (Option C)
const popover = ref(null) // { col, value, x, y }

function openPopover(col, value, event) {
  event.stopPropagation()
  const rect = event.currentTarget.getBoundingClientRect()
  const x = Math.min(rect.left, window.innerWidth - 464)
  popover.value = { col, value: String(value ?? ''), x, y: rect.bottom + 4 }
}

async function copyPopoverValue() {
  if (!popover.value?.value) return
  try { await navigator.clipboard.writeText(popover.value.value) } catch {}
}

function _onPopoverKey(e) { if (e.key === 'Escape') popover.value = null }

watch(popover, (val) => {
  if (val) window.addEventListener('keydown', _onPopoverKey)
  else window.removeEventListener('keydown', _onPopoverKey)
})

// Per-artifact sort state
const sortCol = ref(null)
const sortDir = ref('asc')

function setSort(col) {
  if (sortCol.value === col) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortCol.value = col; sortDir.value = 'asc' }
}

const sortedItems = computed(() => {
  const items = tabData.value.items
  if (!sortCol.value || !items?.length) return items ?? []
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...items].sort((a, b) => {
    const av = a[sortCol.value] ?? ''
    const bv = b[sortCol.value] ?? ''
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' }) * dir
  })
})

async function loadCollection() {
  const { data } = await axios.get(`/api/collections/${collectionId.value}`)
  collection.value = data
  // Sync into store for the card
  collectionsStore.refreshCollection(collectionId.value)
}

async function loadTab() {
  if (activeTab.value === 'timeline') {
    await timelineStore.fetchTimeline(collectionId.value)
    return
  }
  if (activeTab.value === 'system') {
    tabLoading.value = true
    try {
      const { data } = await axios.get(`/api/collections/${collectionId.value}/system-info`)
      systemInfo.value = data
    } catch {
      systemInfo.value = null
    } finally {
      tabLoading.value = false
    }
    return
  }
  tabLoading.value = true
  try {
    const result = await timelineStore.fetchArtifact(collectionId.value, activeTab.value)
    tabData.value = result
  } finally {
    tabLoading.value = false
  }
}

function applyFilters() { loadTab() }

watch(activeTab, () => {
  timelineStore.filters.offset = 0
  sortCol.value = null
  sortDir.value = 'asc'
  artifactSelected.value = new Set()
  artifactPickerRowId.value = null
  lastClickedArtifactId.value = null
  artifactLoadingMore.value = false
  expanded.value = new Set()
  popover.value = null
  loadTab()
})

async function loadMore() {
  if (activeTab.value === 'timeline') {
    await timelineStore.appendTimeline(collectionId.value)
  } else {
    artifactLoadingMore.value = true
    try {
      timelineStore.filters.offset += timelineStore.filters.limit
      const result = await timelineStore.fetchArtifact(collectionId.value, activeTab.value)
      tabData.value.items.push(...result.items)
      tabData.value.total = result.total
    } finally {
      artifactLoadingMore.value = false
    }
  }
}

// Artifact table selection + tag picker
const artifactSelected = ref(new Set())      // Set of row IDs (numbers)
const artifactPickerRowId = ref(null)        // row id with open picker, or 'bulk'
const artifactPickerRect = ref(null)         // BoundingClientRect of the trigger button
const lastClickedArtifactId = ref(null)      // anchor for shift-click range selection
let _shiftCapture = false                    // bridges mousedown → change; not reactive

function captureArtifactShift(event) { _shiftCapture = event.shiftKey }

function toggleArtifactSelect(id) {
  const wasShift = _shiftCapture
  _shiftCapture = false

  if (wasShift && lastClickedArtifactId.value !== null) {
    const ids = sortedItems.value.map(r => r.id)
    const anchorIdx = ids.indexOf(lastClickedArtifactId.value)
    const targetIdx = ids.indexOf(id)
    if (anchorIdx !== -1 && targetIdx !== -1) {
      const [lo, hi] = anchorIdx < targetIdx ? [anchorIdx, targetIdx] : [targetIdx, anchorIdx]
      const next = new Set(artifactSelected.value)
      for (let i = lo; i <= hi; i++) next.add(ids[i])
      artifactSelected.value = next
      return
    }
  }
  if (artifactSelected.value.has(id)) artifactSelected.value.delete(id)
  else artifactSelected.value.add(id)
  artifactSelected.value = new Set(artifactSelected.value)
  lastClickedArtifactId.value = id
}

const allArtifactSelected = computed(() =>
  sortedItems.value.length > 0 && sortedItems.value.every(r => artifactSelected.value.has(r.id))
)

function toggleSelectAllArtifacts() {
  lastClickedArtifactId.value = null
  if (allArtifactSelected.value) artifactSelected.value = new Set()
  else artifactSelected.value = new Set(sortedItems.value.map(r => r.id))
}

function clearArtifactSelection() {
  artifactSelected.value = new Set()
  lastClickedArtifactId.value = null
}

const selectedArtifactRows = computed(() =>
  sortedItems.value.filter(r => artifactSelected.value.has(r.id))
)

const artifactBulkState = computed(() =>
  tagsStore.getBulkTagState(selectedArtifactRows.value.map(r => ({
    artifactType: activeTab.value, artifactId: r.id,
  })))
)

function openArtifactPicker(id, event) {
  event?.stopPropagation()
  if (artifactPickerRowId.value === id) {
    artifactPickerRowId.value = null
    artifactPickerRect.value  = null
  } else {
    artifactPickerRowId.value = id
    artifactPickerRect.value  = event?.currentTarget?.getBoundingClientRect() ?? null
  }
}

function closeArtifactPicker() {
  artifactPickerRowId.value = null
  artifactPickerRect.value  = null
}

function rowPickerApplied(row) {
  return new Set(tagsStore.getRowTags(activeTab.value, row.id).map(t => t.id))
}

async function onArtifactPickerApply(tagId) {
  if (artifactPickerRowId.value === 'bulk') {
    await tagsStore.applyTag(tagId, activeTab.value, [...artifactSelected.value])
  } else {
    await tagsStore.applyTag(tagId, activeTab.value, [artifactPickerRowId.value])
  }
}

async function onArtifactPickerRemove(tagId) {
  if (artifactPickerRowId.value === 'bulk') {
    await tagsStore.removeTag(tagId, activeTab.value, [...artifactSelected.value])
  } else {
    await tagsStore.removeTag(tagId, activeTab.value, [artifactPickerRowId.value])
  }
}

// ── Context menu + file preview + notes ──────────────────────────────────────
const FILE_PREVIEW_FIELD = {
  rcscripts:  'path',
  cron:       'source_file',
  services:   'source_path',
  files:      'path',
  cmdhistory: 'history_file',
}

const artifactContextMenu  = ref(null)  // { x, y, items } | null
const previewTarget        = ref(null)  // { artifactType, path } | null
const artifactNoteTarget   = ref(null)  // { isBulk, ids?, rowId?, initialContent, notesDiffer }
const artifactConfirmTarget = ref(null) // { message, isBulk, ids?, rowId? }

function openArtifactContextMenu(row, mouseEvent) {
  const field = FILE_PREVIEW_FIELD[activeTab.value]
  const path = field ? (row[field] ?? null) : null
  const isBulkCtx = artifactSelected.value.has(row.id) && artifactSelected.value.size > 1

  // ── Note items ──────────────────────────────────────────────────────────────
  const noteItems = []
  if (isBulkCtx) {
    const ids = [...artifactSelected.value]
    const n = ids.length
    const rows = ids.map(id => ({ artifactType: activeTab.value, artifactId: id }))
    const state = notesStore.getBulkNoteState(rows)
    const label = state.hasAny
      ? `Edit note for ${n} row${n === 1 ? '' : 's'}`
      : `Add note to ${n} row${n === 1 ? '' : 's'}`
    noteItems.push({ label, _action: 'note-edit', _isBulk: true, _ids: ids, _state: state })
    if (state.hasAny) {
      noteItems.push({ separator: true })
      noteItems.push({
        label: `Delete note from ${state.noteCount} row${state.noteCount === 1 ? '' : 's'}`,
        _action: 'note-delete', _isBulk: true, _ids: ids, _state: state,
      })
    }
  } else {
    const note = notesStore.getNoteForRow(activeTab.value, row.id)
    noteItems.push({
      label: note ? 'Edit note' : 'Add note',
      _action: 'note-edit', _isBulk: false, _rowId: row.id, _note: note,
    })
    if (note) {
      noteItems.push({ separator: true })
      noteItems.push({ label: 'Delete note', _action: 'note-delete', _isBulk: false, _rowId: row.id })
    }
  }

  artifactContextMenu.value = {
    x: mouseEvent.clientX,
    y: mouseEvent.clientY,
    items: [
      { label: 'Open file preview', disabled: !path, _action: 'preview', _path: path },
      { separator: true },
      ...noteItems,
    ],
  }
}

function onArtifactContextMenuSelect(idx) {
  const item = artifactContextMenu.value?.items[idx]
  artifactContextMenu.value = null
  if (!item || item.disabled || item.separator) return

  if (item._action === 'preview') {
    previewTarget.value = { artifactType: activeTab.value, path: item._path }
    return
  }

  if (item._action === 'note-edit') {
    if (item._isBulk) {
      const s = item._state
      artifactNoteTarget.value = {
        isBulk: true,
        ids: item._ids,
        initialContent: s.allSameContent ? s.commonContent : '',
        notesDiffer: s.hasAny && !s.allSameContent,
      }
    } else {
      artifactNoteTarget.value = {
        isBulk: false,
        rowId: item._rowId,
        initialContent: item._note?.content ?? '',
        notesDiffer: false,
      }
    }
    return
  }

  if (item._action === 'note-delete') {
    if (item._isBulk) {
      const n = item._state.noteCount
      artifactConfirmTarget.value = {
        message: `Delete note from ${n} row${n === 1 ? '' : 's'}?`,
        isBulk: true,
        ids: item._ids,
      }
    } else {
      artifactConfirmTarget.value = {
        message: 'Delete this note?',
        isBulk: false,
        rowId: item._rowId,
      }
    }
  }
}

async function onArtifactNoteSave(content) {
  const t = artifactNoteTarget.value
  artifactNoteTarget.value = null
  if (!t) return
  if (t.isBulk) {
    await notesStore.upsertNote(activeTab.value, t.ids, collectionId.value, content)
  } else {
    await notesStore.upsertNote(activeTab.value, [t.rowId], collectionId.value, content)
  }
}

async function onArtifactNoteDeleteConfirm() {
  const t = artifactConfirmTarget.value
  artifactConfirmTarget.value = null
  if (!t) return
  if (t.isBulk) {
    const ids = t.ids.filter(id => notesStore.getNoteForRow(activeTab.value, id))
    if (ids.length) await notesStore.deleteNote(activeTab.value, ids)
  } else {
    await notesStore.deleteNote(activeTab.value, [t.rowId])
  }
}

onMounted(async () => {
  await loadCollection()
  await Promise.all([
    tagsStore.fetchTags(),
    tagsStore.fetchCollectionTaggings(collectionId.value),
    notesStore.fetchCollectionNotes(collectionId.value),
  ])
  timelineStore.resetFilters()
  loadTab()
})

// Generic artifact columns
const COL_DEFAULTS = {
  processes:  ['pid', 'ppid', 'uid', 'user', 'started', 'command', 'arguments'],
  netconns:   ['proto', 'local_addr', 'local_port', 'remote_addr', 'remote_port', 'state', 'pid'],
  auth:       ['time', 'username', 'result', 'method', 'source', 'destination'],
  cmdhistory: ['time', 'user', 'command', 'history_file'],
  users:      ['username', 'uid', 'gid', 'gecos', 'home', 'shell'],
  files:      ['path', 'mode', 'size', 'uid', 'gid', 'md5', 'inode', 'atime', 'mtime', 'ctime', 'crtime'],
  cron:       ['source_type', 'username', 'minute', 'hour', 'day_of_month', 'month', 'day_of_week', 'command', 'source_file_modified', 'source_file'],
  services:   ['unit_name', 'unit_type', 'description', 'exec_start', 'run_user', 'service_type', 'restart', 'source_dir_type', 'source_file'],
  rcscripts:  ['path', 'source_type', 'run_context', 'username', 'shell', 'interpreter', 'file_size', 'source_file_modified'],
  syslog:     ['timestamp', 'hostname', 'program', 'event_type', 'actor_user', 'target_user', 'source_ip', 'command', 'message', 'source_file'],
}

const colPrefs = useColumnPrefs(COL_DEFAULTS)
const activeCols = computed(() => colPrefs.getOrder(activeTab.value))
const colWidths  = computed(() => colPrefs.getWidths(activeTab.value))

const tableWidth = computed(() => {
  const fixedW = 32 + 192 + 192  // checkbox (2rem) + note (12rem) + tags (12rem)
  return fixedW + activeCols.value.reduce((sum, col) => sum + (colWidths.value[col] ?? 160), 0)
})

// Column drag-to-reorder state
const dragFromIdx = ref(null)
const dragOverIdx = ref(null)

function onColDragStart(idx, event) {
  dragFromIdx.value = idx
  event.dataTransfer.effectAllowed = 'move'
}

function onColDrop(toIdx) {
  if (dragFromIdx.value !== null) {
    colPrefs.reorder(activeTab.value, dragFromIdx.value, toIdx)
  }
  dragFromIdx.value = null
  dragOverIdx.value = null
}

function onColDragEnd() {
  dragFromIdx.value = null
  dragOverIdx.value = null
}

function setDragOver(idx) { dragOverIdx.value = idx }
function clearDragOver()  { dragOverIdx.value = null }

// Column resize state
let _resizeCol   = null
let _resizeStartX = 0
let _resizeStartW = 0

function startResize(col, event) {
  _resizeCol    = col
  _resizeStartX = event.clientX
  _resizeStartW = event.currentTarget.parentElement.getBoundingClientRect().width
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup',   onResizeUp)
}

function onResizeMove(event) {
  if (!_resizeCol) return
  colPrefs.setWidth(activeTab.value, _resizeCol, _resizeStartW + (event.clientX - _resizeStartX))
}

function onResizeUp() {
  _resizeCol = null
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup',   onResizeUp)
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup',   onResizeUp)
  window.removeEventListener('keydown', _onPopoverKey)
})

function fmtCell(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'string' && val.includes('T')) {
    const d = new Date(val)
    if (!isNaN(d)) return d.toISOString().replace('T', ' ').replace('Z', '').slice(0, 19)
  }
  return String(val)
}

function fmtBytes(bytes) {
  if (!bytes) return '—'
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB'
  if (bytes >= 1048576)    return (bytes / 1048576).toFixed(0) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

const SYSTEM_INFO_ROWS = [
  { label: 'Hostname',       field: 'hostname' },
  { label: 'FQDN',           field: 'fqdn' },
  { label: 'Primary IP',     field: 'primary_ip' },
  { label: 'OS',             field: 'os_name' },
  { label: 'Kernel',         field: 'kernel' },
  { label: 'Architecture',   field: 'cpu_arch' },
  { label: 'Timezone',       field: '_timezone' },
  { label: 'Memory',         field: '_memory' },
  { label: 'Domain / Realm', field: 'domain' },
  { label: 'Hardware',       field: 'hardware_model' },
  { label: 'Virtualization', field: 'virtualization' },
]

function sysInfoValue(row) {
  if (!systemInfo.value) return '—'
  if (row.field === '_timezone') {
    const name = systemInfo.value.timezone_name
    const off  = systemInfo.value.timezone_offset
    if (name && off) return `${name} (${off})`
    return name || off || '—'
  }
  if (row.field === '_memory') return fmtBytes(systemInfo.value.memory_bytes)
  return systemInfo.value[row.field] ?? '—'
}
</script>

<template>
  <div class="flex h-[calc(100vh-52px)]">
    <!-- Left sidebar -->
    <aside
      class="shrink-0 border-r border-tn-border flex flex-col bg-tn-surface/50 overflow-hidden transition-[width] duration-200"
      :class="sidebarCollapsed ? 'w-10' : 'w-64'"
    >
      <!-- Header — toggle button is the leftmost element so it stays visible when collapsed -->
      <div class="flex items-start gap-2 p-2 border-b border-tn-border shrink-0">
        <button
          @click="sidebarCollapsed = !sidebarCollapsed"
          class="shrink-0 text-tn-fg-dim hover:text-tn-fg transition-colors p-1 rounded mt-0.5"
          :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-4 h-4 transition-transform duration-200"
            :class="{ 'rotate-180': !sidebarCollapsed }"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fill-rule="evenodd"
              d="M8.293 4.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L11.586 9 8.293 5.707a1 1 0 010-1.414z"
              clip-rule="evenodd" />
          </svg>
        </button>

        <!-- Collection info — clipped by overflow-hidden when collapsed -->
        <div class="flex-1 min-w-0 pt-0.5">
          <div v-if="collection">
            <div class="font-mono font-medium text-tn-fg truncate">{{ collection.hostname }}</div>
            <div class="text-xs text-tn-muted mt-0.5">{{ collection.os }}</div>
            <div class="text-xs text-tn-muted">TZ: {{ collection.timezone_setting }}</div>
          </div>
        </div>
      </div>

      <!-- FilterBar — stays in DOM to preserve filter state -->
      <div class="p-4 flex-1 overflow-y-auto">
        <FilterBar
          :active-tab="activeTab"
          :collection-id="collectionId"
          :collection-timezone="collection?.timezone_setting"
          @apply="applyFilters"
        />
      </div>

      <!-- Processing status -->
      <!--
      <div v-if="collection?.latest_job" class="p-4 border-t border-gray-700 shrink-0">
        <ProcessingStatus
          :job="collection.latest_job"
          :collection-id="collectionId"
          @done="loadTab"
        />
      </div>
            -->
    </aside>


    <!-- Main content -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Tabs -->
      <div class="border-b border-tn-border bg-tn-surface/50 flex">
        <button
          v-for="tab in TABS" :key="tab.key"
          @click="activeTab = tab.key"
          :class="['px-4 py-2.5 text-sm border-b-2 transition-colors',
            activeTab === tab.key
              ? 'border-tn-accent text-tn-accent'
              : 'border-transparent text-tn-fg-dim hover:text-tn-fg']"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Timeline tab -->
      <div v-if="activeTab === 'timeline'" class="flex-1 min-h-0">
        <TimelineTable
          :events="timelineStore.events"
          :total="timelineStore.total"
          :loading="timelineStore.loading"
          :loading-more="timelineStore.loadingMore"
          :collection-id="collectionId"
          @load-more="loadMore"
        />
      </div>

      <!-- System info tab -->
      <div v-else-if="activeTab === 'system'" class="flex-1 min-h-0 overflow-auto p-6">
        <div v-if="tabLoading" class="text-tn-muted text-sm">Loading…</div>
        <div v-else-if="!systemInfo" class="text-tn-muted text-sm">System info not yet available.</div>
        <div v-else class="max-w-2xl">
          <table class="w-full text-xs border-collapse">
            <tbody>
              <tr v-for="row in SYSTEM_INFO_ROWS" :key="row.field"
                  class="border-b border-tn-border">
                <td class="py-2 pr-6 font-mono text-tn-fg-dim whitespace-nowrap w-36">{{ row.label }}</td>
                <td class="py-2 font-mono text-tn-fg break-all">{{ sysInfoValue(row) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Per-artifact tabs -->
      <div v-else class="flex-1 min-h-0 flex flex-col">
        <div class="flex-1 overflow-auto">
          <div v-if="tabLoading" class="p-8 text-center text-tn-muted">Loading…</div>
          <div v-else-if="!tabData.items?.length" class="p-8 text-center text-tn-muted">No records.</div>
          <table v-else class="min-w-full text-xs border-collapse table-fixed" :style="{ width: tableWidth + 'px' }">
            <colgroup>
              <col style="width: 2rem" />
              <col
                v-for="col in activeCols" :key="col"
                :style="{ width: `${colWidths[col] ?? 160}px` }"
              />
              <col style="width: 12rem" />
              <col style="width: 12rem" />
            </colgroup>
            <thead class="sticky top-0 bg-tn-surface border-b border-tn-border">
              <tr>
                <!-- Select-all -->
                <th class="sticky left-0 z-20 bg-tn-surface border-r border-tn-border px-2 py-2">
                  <input
                    type="checkbox"
                    :checked="allArtifactSelected"
                    :indeterminate="artifactSelected.size > 0 && !allArtifactSelected"
                    @change="toggleSelectAllArtifacts"
                    class="accent-tn-accent cursor-pointer"
                  />
                </th>
                <th
                  v-for="(col, idx) in activeCols" :key="col"
                  draggable="true"
                  @click="setSort(col)"
                  @dragstart="onColDragStart(idx, $event)"
                  @dragover.prevent="setDragOver(idx)"
                  @dragleave="clearDragOver()"
                  @drop.prevent="onColDrop(idx)"
                  @dragend="onColDragEnd"
                  class="relative text-left px-3 py-2 font-medium font-mono whitespace-nowrap overflow-hidden cursor-pointer select-none group"
                  :class="[
                    sortCol === col ? 'text-tn-fg' : 'text-tn-fg-dim hover:text-tn-fg',
                    dragOverIdx === idx ? 'bg-tn-selection' : '',
                  ]">
                  <span class="flex items-center gap-1">
                    {{ col }}
                    <span class="text-xs transition-colors"
                          :class="sortCol === col ? 'text-tn-accent' : 'text-tn-muted group-hover:text-tn-fg-dim'">
                      <template v-if="sortCol !== col">⇅</template>
                      <template v-else>{{ sortDir === 'asc' ? '↑' : '↓' }}</template>
                    </span>
                  </span>
                  <!-- Resize handle -->
                  <span
                    class="col-resize-handle"
                    draggable="false"
                    @mousedown.stop.prevent="startResize(col, $event)"
                  />
                </th>
                <!-- Note column header -->
                <th class="text-left px-3 py-2 font-medium font-mono text-tn-fg-dim whitespace-nowrap">note</th>
                <!-- Tags column header -->
                <th class="text-left px-3 py-2 font-medium font-mono text-tn-fg-dim whitespace-nowrap">tags</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="row in sortedItems" :key="row.id">
                <!-- Data row -->
                <tr
                    class="group border-b border-tn-border cursor-pointer"
                    :class="artifactSelected.has(row.id) ? 'bg-tn-selection hover:bg-tn-selection-hover' : 'hover:bg-tn-raised/40'"
                    @click="toggleExpand(row.id)"
                    @contextmenu.prevent="openArtifactContextMenu(row, $event)">
                  <!-- Checkbox — stop propagation so checking doesn't toggle expansion -->
                  <td class="sticky left-0 z-10 border-r border-tn-border px-2 py-1.5" @click.stop
                      :class="artifactSelected.has(row.id) ? 'bg-tn-selection group-hover:bg-tn-selection-hover' : 'bg-tn-bg group-hover:bg-tn-raised/40'">
                    <input
                      type="checkbox"
                      :checked="artifactSelected.has(row.id)"
                      @mousedown="captureArtifactShift"
                      @change="toggleArtifactSelect(row.id)"
                      class="accent-tn-accent cursor-pointer"
                    />
                  </td>
                  <!-- Data cells: flex layout keeps popover button visible alongside truncated text -->
                  <td v-for="col in activeCols" :key="col"
                      class="px-3 py-1.5 font-mono text-tn-fg-dim max-w-0 overflow-hidden group/cell">
                    <div class="flex items-center min-w-0 gap-1">
                      <span class="truncate flex-1 min-w-0 text-xs">{{ fmtCell(row[col]) }}</span>
                      <button
                        v-if="row[col] !== null && row[col] !== undefined && String(row[col]).length > 0"
                        @click.stop="openPopover(col, row[col], $event)"
                        class="shrink-0 opacity-0 group-hover/cell:opacity-100 transition-opacity text-tn-muted hover:text-tn-fg"
                        title="View full value"
                      >
                        <svg class="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M7.5 1.5h3v3m0-3L6 6M4.5 10.5h-3v-3"/>
                        </svg>
                      </button>
                    </div>
                  </td>
                  <!-- Note cell -->
                  <td class="px-3 py-1.5 max-w-48" @click.stop>
                    <span
                      v-if="notesStore.getNoteForRow(activeTab, row.id)"
                      class="text-xs text-tn-fg-dim font-mono truncate block max-w-full cursor-default"
                      :title="notesStore.getNoteForRow(activeTab, row.id)?.content"
                    >{{ notesStore.getNoteForRow(activeTab, row.id)?.content }}</span>
                  </td>
                  <!-- Tags cell -->
                  <td class="px-3 py-1.5 relative" @click.stop>
                    <div class="flex items-center gap-1 flex-wrap">
                      <TagBadge
                        v-for="tag in tagsStore.getRowTags(activeTab, row.id)"
                        :key="tag.id"
                        :tag="tag"
                        removable
                        @remove="tagsStore.removeTag(tag.id, activeTab, [row.id])"
                      />
                      <button
                        @click="openArtifactPicker(row.id, $event)"
                        class="text-tn-muted hover:text-tn-fg-dim text-xs px-1 rounded hover:bg-tn-hover"
                        title="Add tag"
                      >+</button>
                      <TagPicker
                        v-if="artifactPickerRowId === row.id"
                        :applied-ids="rowPickerApplied(row)"
                        :partial-ids="new Set()"
                        :anchor-rect="artifactPickerRect"
                        @apply="onArtifactPickerApply"
                        @remove="onArtifactPickerRemove"
                        @close="closeArtifactPicker"
                      />
                    </div>
                  </td>
                </tr>

                <!-- Expanded detail row: all fields word-wrapped -->
                <tr v-if="expanded.has(row.id)" class="border-b border-tn-border bg-tn-raised/30">
                  <td colspan="100" class="px-6 py-3">
                    <div class="grid gap-x-6 gap-y-1" style="grid-template-columns: minmax(6rem, max-content) 1fr">
                      <template v-for="(val, key) in row" :key="key">
                        <template v-if="key !== 'id' && val !== null && val !== undefined && String(val).trim() !== ''">
                          <div class="text-xs text-tn-fg-dim font-mono whitespace-nowrap py-0.5 select-none">{{ key }}</div>
                          <div class="text-xs text-tn-fg font-mono break-all whitespace-pre-wrap py-0.5 select-text">{{ String(val) }}</div>
                        </template>
                      </template>
                    </div>
                    <div v-if="notesStore.getNoteForRow(activeTab, row.id)" class="mt-2 pt-2 border-t border-tn-border flex items-start gap-3">
                      <span class="text-xs text-tn-fg-dim font-mono shrink-0 select-none">note</span>
                      <span class="text-xs text-tn-fg font-mono break-all whitespace-pre-wrap select-text">{{ notesStore.getNoteForRow(activeTab, row.id)?.content }}</span>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <div class="border-t border-tn-border px-4 py-2 text-xs text-tn-fg-dim shrink-0 flex items-center justify-between">
          <span>Showing {{ tabData.items?.length ?? 0 }} of {{ tabData.total ?? 0 }}</span>
          <div class="flex items-center gap-4">
            <button
              v-if="(tabData.items?.length ?? 0) < (tabData.total ?? 0)"
              @click="loadMore"
              :disabled="artifactLoadingMore"
              class="text-tn-accent hover:text-tn-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >{{ artifactLoadingMore ? 'Loading…' : 'Load more' }}</button>
            <button
              @click="colPrefs.reset(activeTab)"
              class="text-tn-muted hover:text-tn-fg-dim transition-colors"
              title="Reset column order and widths"
            >Reset columns</button>
          </div>
        </div>

        <!-- Bulk action bar -->
        <Transition name="slide-up">
          <div
            v-if="artifactSelected.size > 0"
            class="border-t border-tn-accent bg-tn-selection-bar px-4 py-2 flex items-center gap-3 text-xs shrink-0"
          >
            <span class="text-tn-accent font-mono">
              {{ artifactSelected.size }} row{{ artifactSelected.size === 1 ? '' : 's' }} selected
            </span>
            <div class="relative">
              <button
                @click="openArtifactPicker('bulk', $event)"
                class="px-3 py-1 rounded bg-tn-accent hover:bg-tn-accent-hover text-tn-bg"
              >Tag selected</button>
              <TagPicker
                v-if="artifactPickerRowId === 'bulk'"
                :applied-ids="artifactBulkState.applied"
                :partial-ids="artifactBulkState.partial"
                :anchor-rect="artifactPickerRect"
                @apply="onArtifactPickerApply"
                @remove="onArtifactPickerRemove"
                @close="closeArtifactPicker"
              />
            </div>
            <button
              @click="clearArtifactSelection"
              class="px-3 py-1 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim"
            >Clear</button>
          </div>
        </Transition>
      </div>
    </div>
  </div>

  <!-- Context menu (artifact rows) -->
  <ContextMenu
    v-if="artifactContextMenu"
    :items="artifactContextMenu.items"
    :x="artifactContextMenu.x"
    :y="artifactContextMenu.y"
    @select="onArtifactContextMenuSelect"
    @close="artifactContextMenu = null"
  />

  <!-- File preview modal -->
  <FilePreviewModal
    v-if="previewTarget"
    :collection-id="collectionId"
    :artifact-type="previewTarget.artifactType"
    :path="previewTarget.path"
    @close="previewTarget = null"
  />

  <!-- Note modal -->
  <NoteModal
    v-if="artifactNoteTarget"
    :initial-content="artifactNoteTarget.initialContent"
    :is-bulk="artifactNoteTarget.isBulk"
    :row-count="artifactNoteTarget.isBulk ? artifactNoteTarget.ids.length : 1"
    :notes-differ="artifactNoteTarget.notesDiffer"
    @save="onArtifactNoteSave"
    @close="artifactNoteTarget = null"
  />

  <!-- Confirm delete modal -->
  <ConfirmModal
    v-if="artifactConfirmTarget"
    :message="artifactConfirmTarget.message"
    confirm-label="Delete"
    :destructive="true"
    @confirm="onArtifactNoteDeleteConfirm"
    @close="artifactConfirmTarget = null"
  />

  <!-- Cell value popover (Option C) -->
  <Teleport to="body">
    <template v-if="popover">
      <div class="fixed inset-0 z-40" @click="popover = null" />
      <div
        class="fixed z-50 bg-tn-surface border border-tn-border rounded-lg shadow-2xl w-96"
        style="max-width: min(24rem, 90vw)"
        :style="{ left: popover.x + 'px', top: popover.y + 'px' }"
        @click.stop
      >
        <div class="flex items-center justify-between px-3 pt-2.5 pb-1.5 border-b border-tn-border">
          <span class="text-xs text-tn-fg-dim font-mono">{{ popover.col }}</span>
          <button @click="popover = null" class="text-tn-muted hover:text-tn-fg text-xs ml-4 leading-none">✕</button>
        </div>
        <div class="px-3 py-2.5 text-xs text-tn-fg font-mono break-all whitespace-pre-wrap max-h-64 overflow-y-auto select-text leading-relaxed">{{ popover.value }}</div>
        <div class="px-3 pb-2.5">
          <button @click="copyPopoverValue" class="text-xs text-tn-accent hover:text-tn-accent-hover transition-colors">Copy</button>
        </div>
      </div>
    </template>
  </Teleport>
</template>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.col-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 5px;
  height: 100%;
  cursor: col-resize;
  user-select: none;
  border-right: 2px solid rgba(255, 255, 255, 0.1);
  transition: border-color 0.15s ease, background 0.15s ease;
}
.col-resize-handle:hover,
.col-resize-handle:active {
  background: rgba(96, 165, 250, 0.25);
  border-right-color: rgba(96, 165, 250, 0.7);
}
</style>
