<script setup>
import { ref, onMounted } from 'vue'
import { useCollectionsStore } from '../stores/collections.js'
import CollectionCard from '../components/CollectionCard.vue'
import UploadDialog from '../components/UploadDialog.vue'

const store = useCollectionsStore()
const showUpload = ref(false)

onMounted(() => store.fetchAll())
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-gray-100">Collections</h1>
      <button
        @click="showUpload = true"
        class="px-4 py-2 rounded-lg bg-blue-700 hover:bg-blue-600 text-sm font-medium"
      >
        + Upload
      </button>
    </div>

    <div v-if="store.loading" class="text-center py-16 text-gray-500">Loading…</div>
    <div v-else-if="store.error" class="text-red-400 bg-red-950/30 border border-red-800 rounded p-4">
      {{ store.error }}
    </div>
    <div v-else-if="!store.collections.length" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3">📂</div>
      <div>No collections yet. Upload a UAC archive to get started.</div>
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <CollectionCard v-for="c in store.collections" :key="c.id" :collection="c" />
    </div>

    <UploadDialog v-if="showUpload" @close="showUpload = false" />
  </div>
</template>
