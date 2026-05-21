import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useCollectionsStore = defineStore('collections', () => {
  const collections = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const { data } = await axios.get('/api/collections')
      collections.value = data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function upload(file, threshold = 75, onProgress = null) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await axios.post(`/api/collections/upload?threshold=${threshold}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    })
    await fetchAll()
    return data
  }

  async function remove(id) {
    await axios.delete(`/api/collections/${id}`)
    collections.value = collections.value.filter(c => c.id !== id)
  }

  async function fetchJob(jobId) {
    const { data } = await axios.get(`/api/jobs/${jobId}`)
    return data
  }

  async function refreshCollection(id) {
    const { data } = await axios.get(`/api/collections/${id}`)
    const idx = collections.value.findIndex(c => c.id === id)
    if (idx !== -1) collections.value[idx] = data
    else collections.value.unshift(data)
    return data
  }

  return { collections, loading, error, fetchAll, upload, remove, fetchJob, refreshCollection }
})
