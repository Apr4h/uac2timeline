<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCollectionsStore } from '../stores/collections.js'

const props = defineProps({ collection: Object })
const store = useCollectionsStore()
const router = useRouter()

const confirmDelete = ref(false)
const deleting = ref(false)

const job = computed(() => props.collection.latest_job)

const statusColor = computed(() => {
  if (!job.value) return 'text-gray-500'
  return {
    pending:   'text-yellow-400',
    running:   'text-blue-400',
    completed: 'text-green-400',
    partial:   'text-orange-400',
    failed:    'text-red-400',
  }[job.value.status] || 'text-gray-400'
})

const statusLabel = computed(() => job.value?.status ?? 'no job')

// Poll while processing is active
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
  <div class="bg-gray-900 border border-gray-700 rounded-xl p-5 flex flex-col gap-3">
    <!-- Header -->
    <div class="flex items-start justify-between gap-2">
      <div>
        <div class="font-mono font-medium text-gray-100 truncate">{{ collection.hostname }}</div>
        <div class="text-xs text-gray-500 mt-0.5">{{ collection.os || 'Unknown OS' }} · TZ {{ collection.timezone_setting || '?' }}</div>
      </div>
      <span :class="['text-xs font-mono px-2 py-0.5 rounded-full border', statusColor,
        job?.status === 'completed' ? 'border-green-800 bg-green-950/30' :
        job?.status === 'running'   ? 'border-blue-800 bg-blue-950/30' :
        job?.status === 'failed'    ? 'border-red-800 bg-red-950/30' :
        'border-gray-700 bg-gray-800']">
        {{ statusLabel }}
      </span>
    </div>

    <!-- Artifact counts -->
    <div class="grid grid-cols-5 gap-1 text-center">
      <div v-for="[label, count] in [['proc', collection.process_count], ['net', collection.netconn_count], ['auth', collection.auth_count], ['cmd', collection.cmdhistory_count], ['users', collection.user_count]]"
           :key="label" class="bg-gray-800 rounded p-1.5">
        <div class="text-sm font-mono text-gray-200">{{ count }}</div>
        <div class="text-xs text-gray-500">{{ label }}</div>
      </div>
    </div>

    <!-- Per-artifact job status pills -->
    <div v-if="job?.artifact_jobs?.length" class="flex flex-wrap gap-1">
      <span v-for="aj in job.artifact_jobs" :key="aj.id"
            :class="['text-xs px-2 py-0.5 rounded font-mono',
              aj.status === 'completed' ? 'bg-green-900/50 text-green-300' :
              aj.status === 'running'   ? 'bg-blue-900/50 text-blue-300' :
              aj.status === 'failed'    ? 'bg-red-900/50 text-red-300' :
              'bg-gray-800 text-gray-400']">
        {{ aj.artifact_type }}
        <span v-if="aj.record_count" class="opacity-60">·{{ aj.record_count }}</span>
      </span>
    </div>

    <!-- Actions -->
    <div class="flex gap-2 pt-1">
      <button
        @click="router.push(`/analysis/${collection.id}`)"
        class="flex-1 px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-sm font-medium"
      >
        Analyze
      </button>
      <button v-if="!confirmDelete"
        @click="confirmDelete = true"
        class="px-3 py-1.5 rounded bg-gray-700 hover:bg-red-900 text-sm text-gray-400 hover:text-red-300"
      >
        Delete
      </button>
      <template v-else>
        <button @click="deleteCollection" :disabled="deleting"
          class="px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-sm disabled:opacity-50">
          {{ deleting ? '…' : 'Confirm' }}
        </button>
        <button @click="confirmDelete = false" class="px-3 py-1.5 rounded bg-gray-700 text-sm">Cancel</button>
      </template>
    </div>
  </div>
</template>
