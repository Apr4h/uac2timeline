<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useTimelineStore } from '../stores/timeline.js'
import { useCollectionsStore } from '../stores/collections.js'
import { useTagsStore } from '../stores/tags.js'
import { useColumnPrefs } from '../composables/useColumnPrefs.js'
import TimelineTable from '../components/TimelineTable.vue'
import FilterBar from '../components/FilterBar.vue'
import ProcessingStatus from '../components/ProcessingStatus.vue'
import TagBadge from '../components/TagBadge.vue'
import TagPicker from '../components/TagPicker.vue'

const route = useRoute()
const router = useRouter()
const timelineStore = useTimelineStore()
const collectionsStore = useCollectionsStore()
const tagsStore = useTagsStore()

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
]

// System info tab state
const systemInfo = ref(null)

// Per-artifact tab state
const tabData = ref({ items: [], total: 0 })
const tabLoading = ref(false)

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
  loadTab()
})

async function loadMore() {
  if (activeTab.value === 'timeline') {
    timelineStore.filters.offset += timelineStore.filters.limit
    const { data } = await axios.get(`/api/collections/${collectionId.value}/timeline`, {
      params: {
        limit: timelineStore.filters.limit,
        offset: timelineStore.filters.offset,
        ...(timelineStore.filters.start && { start: timelineStore.filters.start }),
        ...(timelineStore.filters.end   && { end:   timelineStore.filters.end   }),
        ...(timelineStore.filters.filterStr && { filter: timelineStore.filters.filterStr }),
        ...(timelineStore.filters.regex && { regex:  timelineStore.filters.regex }),
      }
    })
    timelineStore.events.push(...data.events)
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

onMounted(async () => {
  await loadCollection()
  await tagsStore.fetchTags()
  await tagsStore.fetchCollectionTaggings(collectionId.value)
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
  files:      ['path', 'mode', 'size', 'uid', 'gid', 'atime', 'mtime', 'ctime'],
  cron:       ['source_type', 'username', 'minute', 'hour', 'day_of_month', 'month', 'day_of_week', 'command', 'source_file_modified', 'source_file'],
  services:   ['unit_name', 'unit_type', 'description', 'exec_start', 'run_user', 'service_type', 'restart', 'source_dir_type', 'source_file'],
}

const colPrefs = useColumnPrefs(COL_DEFAULTS)
const activeCols = computed(() => colPrefs.getOrder(activeTab.value))
const colWidths  = computed(() => colPrefs.getWidths(activeTab.value))

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
          <button @click="router.push('/collections')" class="text-xs text-tn-fg-dim hover:text-tn-fg mb-3 flex items-center gap-1">
            ← Collections
          </button>
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
          <table v-else class="w-full text-xs border-collapse table-fixed">
            <colgroup>
              <col style="width: 2rem" />
              <col
                v-for="col in activeCols" :key="col"
                :style="colWidths[col] ? { width: `${colWidths[col]}px` } : {}"
              />
              <col style="width: 12rem" />
            </colgroup>
            <thead class="sticky top-0 bg-tn-surface border-b border-tn-border">
              <tr>
                <!-- Select-all -->
                <th class="px-2 py-2">
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
                  class="relative text-left px-3 py-2 font-medium font-mono whitespace-nowrap cursor-pointer select-none group"
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
                <!-- Tags column header -->
                <th class="text-left px-3 py-2 font-medium font-mono text-tn-fg-dim whitespace-nowrap">tags</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in sortedItems" :key="row.id"
                  :class="[
                    'border-b border-tn-border',
                    artifactSelected.has(row.id) ? 'bg-tn-selection hover:bg-tn-selection-hover' : 'hover:bg-tn-raised/40',
                  ]">
                <!-- Checkbox -->
                <td class="px-2 py-1.5">
                  <input
                    type="checkbox"
                    :checked="artifactSelected.has(row.id)"
                    @mousedown="captureArtifactShift"
                    @change="toggleArtifactSelect(row.id)"
                    class="accent-tn-accent cursor-pointer"
                  />
                </td>
                <td v-for="col in activeCols" :key="col"
                    class="px-3 py-1.5 font-mono text-tn-fg-dim truncate"
                    :title="String(row[col] ?? '')">
                  {{ fmtCell(row[col]) }}
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
            </tbody>
          </table>
        </div>
        <div class="border-t border-tn-border px-4 py-2 text-xs text-tn-fg-dim shrink-0 flex items-center justify-between">
          <span>Showing {{ tabData.items?.length ?? 0 }} of {{ tabData.total ?? 0 }}</span>
          <button
            @click="colPrefs.reset(activeTab)"
            class="text-tn-muted hover:text-tn-fg-dim transition-colors"
            title="Reset column order and widths"
          >Reset columns</button>
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
}
.col-resize-handle:hover {
  background: rgba(96, 165, 250, 0.5);
}
</style>
