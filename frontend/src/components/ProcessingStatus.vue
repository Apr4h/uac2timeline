<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useCollectionsStore } from '../stores/collections.js'
import axios from 'axios'

const props = defineProps({ job: Object, collectionId: Number })
const emit = defineEmits(['done'])
const store = useCollectionsStore()

const expanded = ref(null)
const logs = ref([])
const logsLoading = ref(false)

const isActive = computed(() => ['pending', 'running'].includes(props.job?.status))

let pollTimer = null
function startPoll() {
  if (pollTimer || !isActive.value) return
  pollTimer = setInterval(async () => {
    await store.refreshCollection(props.collectionId)
    if (!isActive.value) {
      stopPoll()
      emit('done')
    }
  }, 2000)
}
function stopPoll() { clearInterval(pollTimer); pollTimer = null }

watch(() => props.job?.status, (s) => {
  if (['pending', 'running'].includes(s)) startPoll()
  else stopPoll()
}, { immediate: true })

onUnmounted(stopPoll)

async function showLogs(aj) {
  if (expanded.value === aj.id) { expanded.value = null; return }
  expanded.value = aj.id
  logsLoading.value = true
  try {
    const { data } = await axios.get(`/api/jobs/${props.job.id}/logs?artifact_type=${aj.artifact_type}`)
    logs.value = data
  } finally {
    logsLoading.value = false
  }
}

const STATUS_ICON = { completed: '✓', failed: '✗', running: '⟳', pending: '◦', partial: '⚠' }
const STATUS_COLOR = {
  completed: 'text-green-400',
  failed:    'text-red-400',
  running:   'text-blue-400 animate-spin inline-block',
  pending:   'text-gray-500',
  partial:   'text-orange-400',
}
</script>

<template>
  <div v-if="job" class="bg-gray-900 border border-gray-700 rounded-xl p-4">
    <div class="flex items-center gap-2 mb-3">
      <span :class="['font-mono text-sm', STATUS_COLOR[job.status]]">
        {{ STATUS_ICON[job.status] }}
      </span>
      <span class="text-sm text-gray-300 font-medium">Processing</span>
      <span class="text-xs text-gray-500 ml-auto">Job #{{ job.id }}</span>
    </div>

    <div class="flex flex-col gap-1">
      <div
        v-for="aj in job.artifact_jobs"
        :key="aj.id"
        class="rounded border border-gray-700 overflow-hidden"
      >
        <button
          @click="showLogs(aj)"
          class="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-gray-800 text-left"
        >
          <span :class="['font-mono text-xs', STATUS_COLOR[aj.status]]">
            {{ STATUS_ICON[aj.status] }}
          </span>
          <span class="text-xs font-mono text-gray-300 flex-1">{{ aj.artifact_type }}</span>
          <span v-if="aj.record_count" class="text-xs text-gray-500">{{ aj.record_count }} records</span>
          <span v-if="aj.error_message" class="text-xs text-red-400 truncate max-w-32" :title="aj.error_message">
            {{ aj.error_message }}
          </span>
          <span class="text-gray-600 text-xs">{{ expanded === aj.id ? '▲' : '▼' }}</span>
        </button>

        <!-- Log entries -->
        <div v-if="expanded === aj.id" class="bg-gray-950 border-t border-gray-700 max-h-48 overflow-y-auto">
          <div v-if="logsLoading" class="px-3 py-2 text-xs text-gray-500">Loading…</div>
          <div v-else-if="!logs.length" class="px-3 py-2 text-xs text-gray-500">No log entries.</div>
          <div v-else v-for="log in logs" :key="log.id"
               class="px-3 py-0.5 font-mono text-xs border-b border-gray-800 last:border-0"
               :class="{
                 'text-red-400': log.level === 'ERROR',
                 'text-yellow-400': log.level === 'WARNING',
                 'text-gray-300': log.level === 'INFO',
                 'text-gray-500': log.level === 'DEBUG',
               }">
            <span class="text-gray-600 mr-2">{{ log.level }}</span>{{ log.message }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
