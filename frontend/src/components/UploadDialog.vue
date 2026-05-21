<script setup>
import { ref } from 'vue'
import { useCollectionsStore } from '../stores/collections.js'
import { useRouter } from 'vue-router'

const emit = defineEmits(['close'])
const store = useCollectionsStore()
const router = useRouter()

const dragging = ref(false)
const file = ref(null)
const threshold = ref(75)
const uploading = ref(false)
const progress = ref(0)
const errorMsg = ref('')

function onDrop(e) {
  dragging.value = false
  const f = e.dataTransfer.files[0]
  if (f) file.value = f
}

function onPick(e) {
  file.value = e.target.files[0] || null
}

async function submit() {
  if (!file.value) return
  uploading.value = true
  errorMsg.value = ''
  progress.value = 0
  try {
    const result = await store.upload(file.value, threshold.value, e => {
      progress.value = Math.round((e.loaded / e.total) * 100)
    })
    emit('close')
    router.push(`/analysis/${result.collection_id}`)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="emit('close')">
    <div class="bg-tn-surface border border-tn-border rounded-xl shadow-2xl w-full max-w-md p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-tn-fg">Upload UAC Collection</h2>
        <button @click="emit('close')" class="text-tn-fg-dim hover:text-tn-fg">✕</button>
      </div>

      <!-- Drop zone -->
      <div
        class="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors"
        :class="dragging ? 'border-tn-accent bg-tn-selection' : 'border-tn-border-strong hover:border-tn-fg-dim'"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="onDrop"
        @click="$refs.fileInput.click()"
      >
        <input ref="fileInput" type="file" accept=".zip,.tar.gz,.tgz,.tar.bz2,.tar" class="hidden" @change="onPick" />
        <div v-if="file" class="text-green-400 font-mono text-sm truncate">{{ file.name }}</div>
        <div v-else class="text-tn-fg-dim text-sm">
          <div class="text-2xl mb-2">📁</div>
          <div>Drop a <span class="font-mono">.zip</span> or <span class="font-mono">.tar.gz</span> archive here</div>
          <div class="text-tn-muted text-xs mt-1">or click to browse</div>
        </div>
      </div>

      <!-- Threshold -->
      <div class="mt-4">
        <label class="text-xs text-tn-fg-dim block mb-1">
          Parse threshold: <span class="text-tn-fg font-mono">{{ threshold }}%</span>
        </label>
        <input type="range" v-model.number="threshold" min="1" max="100" class="w-full accent-tn-accent" />
      </div>

      <!-- Error -->
      <div v-if="errorMsg" class="mt-3 text-sm text-red-400 bg-red-950/40 border border-red-800 rounded p-2">
        {{ errorMsg }}
      </div>

      <!-- Progress -->
      <div v-if="uploading" class="mt-3">
        <div class="h-1.5 bg-tn-raised rounded-full overflow-hidden">
          <div class="h-full bg-tn-accent transition-all" :style="`width: ${progress}%`" />
        </div>
        <div class="text-xs text-tn-fg-dim mt-1">Uploading… {{ progress }}%</div>
      </div>

      <div class="flex gap-3 mt-5">
        <button @click="emit('close')" class="flex-1 px-4 py-2 rounded bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim text-sm">
          Cancel
        </button>
        <button
          @click="submit"
          :disabled="!file || uploading"
          class="flex-1 px-4 py-2 rounded bg-tn-accent hover:bg-tn-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-tn-bg text-sm font-medium"
        >
          {{ uploading ? 'Uploading…' : 'Upload & Process' }}
        </button>
      </div>
    </div>
  </div>
</template>
