<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCollectionsStore } from '../stores/collections.js'
import { useTagsStore } from '../stores/tags.js'
import ExportDialog from './ExportDialog.vue'

const props = defineProps({ collection: Object })
const store = useCollectionsStore()
const router = useRouter()

const tagsStore = useTagsStore()
const confirmDelete = ref(false)
const deleting = ref(false)
const showExport = ref(false)

const job = computed(() => props.collection.latest_job)

const statusColor = computed(() => {
  if (!job.value) return 'text-tn-muted'
  return {
    pending:   'text-yellow-400',
    running:   'text-tn-accent',
    completed: 'text-green-400',
    partial:   'text-orange-400',
    failed:    'text-red-400',
  }[job.value.status] || 'text-tn-fg-dim'
})

// Map artifact_type → job status for per-pill coloring
const jobStatusByType = computed(() => {
  const m = {}
  for (const aj of job.value?.artifact_jobs ?? []) m[aj.artifact_type] = aj.status
  return m
})

const ARTIFACTS = [
  { type: 'processes',  label: 'proc',    key: 'process_count' },
  { type: 'netconns',   label: 'net',     key: 'netconn_count' },
  { type: 'auth',       label: 'auth',    key: 'auth_count' },
  { type: 'cmdhistory', label: 'cmd',     key: 'cmdhistory_count' },
  { type: 'users',      label: 'users',   key: 'user_count' },
  { type: 'cron',       label: 'cron',    key: 'cron_count' },
  { type: 'systemd',    label: 'services',     key: 'systemd_count' },
  { type: 'rcscripts',  label: 'rcscripts', key: 'rcscripts_count' },
  { type: 'syslog',     label: 'syslog',  key: 'syslog_count' },
]

function artifactPillClass(type) {
  const s = jobStatusByType.value[type]
  if (s === 'completed') return 'bg-green-900/40 text-green-300'
  if (s === 'running')   return 'bg-tn-selection text-tn-accent'
  if (s === 'failed')    return 'bg-red-900/40 text-red-300'
  if (s === 'pending')   return 'bg-yellow-900/30 text-yellow-400'
  return 'bg-tn-raised text-tn-fg-dim'
}

const statusLabel = computed(() => job.value?.status ?? 'no job')

let pollTimer = null
const isActive = computed(() => ['pending', 'running'].includes(job.value?.status))

function startPolling() {
  if (pollTimer || !isActive.value || !job.value) return
  pollTimer = setInterval(async () => {
    await store.refreshCollection(props.collection.id)
    if (!isActive.value) stopPolling()
  }, 2000)
}

function stopPolling() {
  clearInterval(pollTimer)
  pollTimer = null
}

if (isActive.value) startPolling()
onUnmounted(stopPolling)

async function deleteCollection() {
  deleting.value = true
  try {
    await store.remove(props.collection.id)
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}
</script>

<template>
  <div class="bg-tn-surface border border-tn-border rounded-xl p-5 flex flex-col gap-3">
    <!-- Header -->
    <div class="flex items-start justify-between gap-2">
      <div>
        <div class="font-mono font-medium text-tn-fg truncate">{{ collection.hostname }}</div>
        <div class="text-xs text-tn-muted mt-0.5">{{ collection.os || 'Unknown OS' }} · TZ {{ collection.timezone_setting || '?' }}</div>
        <div v-if="collection.primary_ip_address" class="text-xs text-tn-muted font-mono">{{ collection.primary_ip_address }}</div>
      </div>
      <span :class="['text-xs font-mono px-2 py-0.5 rounded-full border', statusColor,
        job?.status === 'completed' ? 'border-green-800 bg-green-950/30' :
        job?.status === 'running'   ? 'border-tn-accent bg-tn-selection' :
        job?.status === 'failed'    ? 'border-red-800 bg-red-950/30' :
        'border-tn-border bg-tn-raised']">
        {{ statusLabel }}
      </span>
    </div>

    <!-- Artifact counts (colored by job status when a job is present) -->
    <div class="flex flex-wrap gap-1">
      <span v-for="a in ARTIFACTS" :key="a.type"
            :class="['text-xs px-2 py-0.5 rounded font-mono', artifactPillClass(a.type)]">
        {{ a.label }}<span class="opacity-60 ml-0.5">·{{ collection[a.key] ?? 0 }}</span>
      </span>
    </div>

    <!-- Actions -->
    <div class="flex gap-2 pt-1">
      <button
        @click="router.push(`/analysis/${collection.id}`)"
        class="flex-1 px-3 py-1.5 rounded bg-tn-accent hover:bg-tn-accent-hover text-tn-bg text-sm font-medium"
      >
        Analyze
      </button>
      <button
        v-if="tagsStore.tags.length > 0"
        @click="showExport = true"
        class="px-3 py-1.5 rounded bg-tn-raised hover:bg-tn-hover border border-tn-border text-tn-fg-dim hover:text-tn-fg text-sm transition-colors"
        title="Export tagged rows to Excel"
      >
        Export
      </button>
      <button v-if="!confirmDelete"
        @click="confirmDelete = true"
        class="px-3 py-1.5 rounded bg-tn-hover hover:bg-red-900 text-sm text-tn-fg-dim hover:text-red-300"
      >
        Delete
      </button>
      <template v-else>
        <button @click="deleteCollection" :disabled="deleting"
          class="px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-sm disabled:opacity-50">
          {{ deleting ? '…' : 'Confirm' }}
        </button>
        <button @click="confirmDelete = false" class="px-3 py-1.5 rounded bg-tn-hover text-sm">Cancel</button>
      </template>
    </div>
  </div>

  <ExportDialog
    v-if="showExport"
    :collection-id="collection.id"
    :collection-hostname="collection.hostname"
    @close="showExport = false"
  />
</template>
