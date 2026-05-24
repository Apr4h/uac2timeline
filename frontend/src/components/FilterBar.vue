<script setup>
import { ref, computed, watch } from 'vue'
import { useTimelineStore } from '../stores/timeline.js'
import { useTagsStore } from '../stores/tags.js'
import { useSavedFilters } from '../composables/useSavedFilters.js'

const props = defineProps({
  activeTab: String,
  collectionId: Number,
  collectionTimezone: String,
})
const emit = defineEmits(['apply'])
const store = useTimelineStore()
const tagsStore = useTagsStore()

const isCollapsed = ref(false)
const ALL_TYPES = ['processes', 'auth', 'cmdhistory', 'netconns', 'files', 'cron', 'services', 'rcscripts', 'syslog']

const COLUMN_LISTS = {
  timeline:   ['type', 'hostname', 'ts_description', 'summary', 'assoc_user', 'source_ip', 'dest_ip', 'md5'],
  processes:  ['pid', 'ppid', 'uid', 'user', 'command', 'arguments'],
  netconns:   ['proto', 'local_addr', 'local_port', 'remote_addr', 'remote_port', 'state', 'pid'],
  auth:       ['username', 'result', 'method', 'source', 'destination'],
  cmdhistory: ['user', 'command', 'history_file'],
  users:      ['username', 'uid', 'gid', 'gecos', 'home', 'shell'],
  files:      ['path', 'mode', 'size', 'uid', 'gid', 'md5', 'inode'],
  cron:       ['source_type', 'username', 'command', 'source_file'],
  services:   ['unit_name', 'unit_type', 'description', 'exec_start', 'run_user', 'service_type', 'restart', 'source_dir_type'],
  rcscripts:  ['path', 'source_type', 'run_context', 'username', 'shell', 'interpreter'],
  syslog:     ['hostname', 'program', 'event_type', 'actor_user', 'target_user', 'source_ip', 'command', 'message', 'source_file'],
}

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

const TAG_CHIP_ACTIVE = {
  red:    'ring-1 ring-red-400',
  orange: 'ring-1 ring-orange-400',
  yellow: 'ring-1 ring-yellow-400',
  green:  'ring-1 ring-green-400',
  teal:   'ring-1 ring-teal-400',
  blue:   'ring-1 ring-blue-400',
  purple: 'ring-1 ring-purple-400',
  pink:   'ring-1 ring-pink-400',
  gray:   'ring-1 ring-tn-border-strong',
}

function isValidIso(str) {
  if (!str?.trim()) return true
  return !isNaN(new Date(str.trim().replace(/\s/, 'T')).getTime())
}

const startValid = computed(() => isValidIso(store.filters.start))
const endValid   = computed(() => isValidIso(store.filters.end))
const canApply   = computed(() => startValid.value && endValid.value)

function tsClass(valid) {
  return valid
    ? 'border-tn-border-strong focus:border-tn-accent'
    : 'border-red-500 focus:border-red-400'
}

function toggleType(t) {
  const idx = store.filters.types.indexOf(t)
  if (idx === -1) store.filters.types.push(t)
  else if (store.filters.types.length > 1) store.filters.types.splice(idx, 1)
}

function toggleTag(id) {
  const idx = store.filters.tagIds.indexOf(id)
  if (idx === -1) store.filters.tagIds.push(id)
  else store.filters.tagIds.splice(idx, 1)
}

const PAGE_SIZES = [10, 100, 500, 1000, 2000]

function apply() {
  if (!canApply.value) return
  store.filters.offset = 0
  emit('apply')
}

function setLimit(n) {
  store.filters.limit = n
  store.filters.offset = 0
  emit('apply')
}

function reset() {
  store.resetFilters()
  emit('apply')
}

// ── Column filter rule builder ────────────────────────────────────────────────

const activeRuleCount = computed(() =>
  store.filters.colFilters.filter(r => r.col && r.pattern).length
)

function availableCols() {
  return COLUMN_LISTS[props.activeTab] ?? COLUMN_LISTS.timeline
}

function addRule() {
  const cols = availableCols()
  store.filters.colFilters.push({ col: cols[0] ?? '', mode: 'inc', pattern: '', isRegex: false })
}

function removeRule(idx) {
  store.filters.colFilters.splice(idx, 1)
}

function toggleMode(rule) {
  rule.mode = rule.mode === 'inc' ? 'exc' : 'inc'
}

function toggleRegex(rule) {
  rule.isRegex = !rule.isRegex
}

// Reset rules when tab changes so stale column names don't carry over
watch(() => props.activeTab, () => {
  store.filters.colFilters = []
})

// ── Saved filters ─────────────────────────────────────────────────────────────

const { saved, load: loadSaved, save: doSave, remove: doRemove } = useSavedFilters()

watch(() => props.collectionId, (id) => { if (id) loadSaved(id) }, { immediate: true })

const showSaveForm = ref(false)
const savingName   = ref('')

function openSaveForm() {
  savingName.value = ''
  showSaveForm.value = true
}

function cancelSave() {
  showSaveForm.value = false
  savingName.value = ''
}

function confirmSave() {
  const name = savingName.value.trim()
  if (!name) return
  doSave(props.collectionId, name, {
    colFilters: store.filters.colFilters.map(r => ({ ...r })),
    start:      store.filters.start,
    end:        store.filters.end,
    types:      [...store.filters.types],
    tagIds:     [...store.filters.tagIds],
  })
  showSaveForm.value = false
  savingName.value = ''
}

function loadEntry(entry) {
  store.filters.colFilters = (entry.filters.colFilters ?? []).map(r => ({ ...r }))
  store.filters.start      = entry.filters.start   ?? ''
  store.filters.end        = entry.filters.end     ?? ''
  store.filters.types      = [...(entry.filters.types  ?? ALL_TYPES)]
  store.filters.tagIds     = [...(entry.filters.tagIds ?? [])]
  store.filters.offset     = 0
  emit('apply')
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs font-semibold text-tn-fg-dim uppercase tracking-wider">Filters</span>
      <button
        @click="isCollapsed = !isCollapsed"
        class="relative text-tn-fg-dim hover:text-tn-fg transition-colors p-0.5 rounded"
        :title="isCollapsed ? 'Expand filters' : 'Collapse filters'"
      >
        <!-- active-rule indicator dot when collapsed -->
        <span
          v-if="isCollapsed && activeRuleCount > 0"
          class="absolute -top-1 -right-1 min-w-3.5 h-3.5 px-0.5 rounded-full bg-tn-accent text-tn-bg text-[9px] font-bold flex items-center justify-center leading-none"
        >{{ activeRuleCount }}</span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-3.5 h-3.5 transition-transform duration-200"
          :class="{ 'rotate-180': isCollapsed }"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd"
            d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
            clip-rule="evenodd" />
        </svg>
      </button>
    </div>

    <Transition name="slide-fade">
      <div v-show="!isCollapsed" class="flex flex-col gap-3">

        <!-- Column filter rule builder -->
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <label class="text-xs text-tn-fg-dim">Column filters</label>
            <button
              @click="addRule"
              class="text-xs text-tn-accent hover:text-tn-accent-hover transition-colors"
            >+ Add rule</button>
          </div>

          <div v-if="store.filters.colFilters.length === 0" class="text-xs text-tn-muted italic">
            No filters — all rows shown.
          </div>

          <div v-for="(rule, idx) in store.filters.colFilters" :key="idx"
            class="mb-2 rounded border border-tn-border/50 bg-tn-raised/40 px-2 py-1.5 flex flex-col gap-1"
          >
            <!-- Row 1: column selector + mode toggle -->
            <div class="flex gap-1 items-center">
              <select
                v-model="rule.col"
                class="flex-1 min-w-0 bg-tn-raised border border-tn-border-strong rounded px-1.5 py-1 text-xs text-tn-fg font-mono focus:outline-none focus:border-tn-accent"
              >
                <option v-for="col in availableCols()" :key="col" :value="col">{{ col }}</option>
              </select>

              <!-- +/− mode toggle -->
              <button
                @click="toggleMode(rule)"
                :class="['shrink-0 w-6 h-6 rounded text-sm font-bold transition-colors flex items-center justify-center',
                  rule.mode === 'inc'
                    ? 'bg-green-900/50 text-green-300 hover:bg-green-900/80'
                    : 'bg-red-900/50 text-red-300 hover:bg-red-900/80']"
                :title="rule.mode === 'inc' ? 'Inclusive — row must match' : 'Exclusive — row must NOT match'"
              >{{ rule.mode === 'inc' ? '+' : '−' }}</button>
            </div>

            <!-- Row 2: pattern input + regex icon + remove -->
            <div class="flex gap-1 items-center">
              <input
                v-model="rule.pattern"
                @keyup.enter="apply"
                placeholder="pattern…"
                :class="['flex-1 min-w-0 bg-tn-raised border border-tn-border-strong rounded px-2 py-1 text-xs text-tn-fg font-mono placeholder-tn-muted focus:outline-none focus:border-tn-accent',
                  rule.isRegex ? 'italic' : '']"
              />

              <!-- Regex toggle — /…/ icon -->
              <button
                @click="toggleRegex(rule)"
                :class="['shrink-0 w-6 h-6 rounded text-xs font-mono font-semibold transition-colors flex items-center justify-center',
                  rule.isRegex
                    ? 'bg-tn-accent text-tn-bg'
                    : 'bg-tn-raised text-tn-fg-dim hover:bg-tn-hover']"
                title="Toggle regular expression"
              >/./</button>

              <!-- Remove -->
              <button
                @click="removeRule(idx)"
                class="shrink-0 w-6 h-6 rounded text-tn-muted hover:text-red-400 hover:bg-red-900/30 transition-colors flex items-center justify-center text-sm leading-none"
                title="Remove rule"
              >✕</button>
            </div>
          </div>
        </div>

        <template v-if="activeTab === 'timeline'">
          <div>
            <label class="text-xs text-tn-fg-dim block mb-1">Start time</label>
            <input
              v-model="store.filters.start"
              @keyup.enter="apply"
              placeholder="2024-01-15T09:00:00"
              :class="['w-full bg-tn-raised border rounded px-3 py-1.5 text-sm font-mono text-tn-fg placeholder-tn-muted focus:outline-none', tsClass(startValid)]"
            />
            <p v-if="!startValid" class="text-xs text-red-400 mt-1">Invalid timestamp</p>
          </div>

          <div>
            <label class="text-xs text-tn-fg-dim block mb-1">End time</label>
            <input
              v-model="store.filters.end"
              @keyup.enter="apply"
              placeholder="2024-01-15T18:00:00"
              :class="['w-full bg-tn-raised border rounded px-3 py-1.5 text-sm font-mono text-tn-fg placeholder-tn-muted focus:outline-none', tsClass(endValid)]"
            />
            <p v-if="!endValid" class="text-xs text-red-400 mt-1">Invalid timestamp</p>
            <p v-if="collectionTimezone" class="text-xs text-tn-muted font-mono mt-1">
              Collection TZ: {{ collectionTimezone }}
            </p>
          </div>

          <div>
            <label class="text-xs text-tn-fg-dim block mb-2">Artifact types</label>
            <div class="flex flex-wrap gap-1.5">
              <button v-for="t in ALL_TYPES" :key="t"
                @click="toggleType(t)"
                :class="['px-2.5 py-1 rounded text-xs font-mono transition-colors',
                  store.filters.types.includes(t)
                    ? 'bg-tn-accent text-tn-bg'
                    : 'bg-tn-raised text-tn-fg-dim hover:bg-tn-hover']"
              >{{ t }}</button>
            </div>
          </div>
        </template>

        <div>
          <label class="text-xs text-tn-fg-dim block mb-2">Page size</label>
          <div class="flex gap-1.5">
            <button
              v-for="n in PAGE_SIZES" :key="n"
              @click="setLimit(n)"
              :class="['px-2.5 py-1 rounded text-xs font-mono transition-colors',
                store.filters.limit === n
                  ? 'bg-tn-accent text-tn-bg'
                  : 'bg-tn-raised text-tn-fg-dim hover:bg-tn-hover']"
            >{{ n }}</button>
          </div>
        </div>

        <div v-if="tagsStore.tags.length > 0">
          <label class="text-xs text-tn-fg-dim block mb-2">Tags</label>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="tag in tagsStore.tags"
              :key="tag.id"
              @click="toggleTag(tag.id)"
              :class="[
                'inline-flex items-center text-xs font-mono px-1.5 py-0.5 rounded border transition-all',
                TAG_CHIP_CLASSES[tag.color] ?? TAG_CHIP_CLASSES.gray,
                store.filters.tagIds.includes(tag.id)
                  ? (TAG_CHIP_ACTIVE[tag.color] ?? TAG_CHIP_ACTIVE.gray)
                  : 'opacity-50 hover:opacity-75',
              ]"
            >{{ tag.name }}</button>
          </div>
        </div>

        <div class="flex gap-2 pt-1">
          <button
            @click="apply"
            :disabled="!canApply"
            class="flex-1 px-3 py-1.5 rounded bg-tn-accent hover:bg-tn-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-tn-bg text-sm transition-colors"
          >Apply</button>
          <button @click="reset" class="px-3 py-1.5 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim text-sm">Reset</button>
        </div>

        <div v-if="collectionId" class="pt-2 border-t border-tn-border/60">

          <template v-if="showSaveForm">
            <label class="text-xs text-tn-fg-dim block mb-1">Filter name</label>
            <div class="flex gap-1">
              <input
                v-model="savingName"
                placeholder="e.g. IOC hunt"
                @keyup.enter="confirmSave"
                @keyup.esc="cancelSave"
                autofocus
                class="flex-1 min-w-0 bg-tn-raised border border-tn-border-strong rounded px-2 py-1 text-xs text-tn-fg placeholder-tn-muted focus:outline-none focus:border-tn-accent"
              />
              <button
                @click="confirmSave"
                :disabled="!savingName.trim()"
                class="shrink-0 px-2 py-1 rounded bg-tn-accent hover:bg-tn-accent-hover disabled:opacity-40 text-xs text-tn-bg"
              >Save</button>
              <button
                @click="cancelSave"
                class="shrink-0 px-2 py-1 rounded bg-tn-hover hover:bg-tn-border-strong text-xs text-tn-fg-dim"
              >✕</button>
            </div>
          </template>

          <ul
            v-if="saved.length"
            class="space-y-0.5 max-h-44 overflow-y-auto"
            :class="showSaveForm ? 'mt-2' : ''"
          >
            <li
              v-for="entry in saved"
              :key="entry.id"
              class="flex items-center gap-1 group rounded px-1 hover:bg-tn-raised/60"
            >
              <button
                @click="loadEntry(entry)"
                class="flex-1 min-w-0 text-left text-xs text-tn-fg-dim hover:text-tn-accent truncate py-1 transition-colors"
                :title="`${entry.name} — saved ${new Date(entry.savedAt).toLocaleDateString()}`"
              >{{ entry.name }}</button>
              <button
                @click="doRemove(collectionId, entry.id)"
                class="shrink-0 text-tn-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1 py-1 text-xs leading-none"
                title="Delete saved filter"
              >✕</button>
            </li>
          </ul>

          <button
            v-if="!showSaveForm"
            @click="openSaveForm"
            class="mt-1 w-full text-left text-xs text-tn-muted hover:text-tn-fg-dim py-0.5 transition-colors"
          >+ Save current filters</button>
        </div>

      </div>
    </Transition>
  </div>
</template>

<style scoped>
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: opacity 0.2s ease, max-height 0.2s ease;
  overflow: hidden;
  max-height: 1200px;
}
.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
