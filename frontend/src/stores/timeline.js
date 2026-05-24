import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import axios from 'axios'

const ALL_ARTIFACT_TYPES = ['processes', 'auth', 'cmdhistory', 'netconns', 'files', 'cron', 'services', 'rcscripts', 'syslog']

// Normalise ISO text before sending: space → T, Z → +00:00
function normaliseDateParam(s) {
  if (!s?.trim()) return s
  return s.trim().replace(/\s/, 'T').replace(/Z$/i, '+00:00')
}

export const useTimelineStore = defineStore('timeline', () => {
  const events = ref([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref(null)

  const filters = reactive({
    start: '',
    end: '',
    types: [...ALL_ARTIFACT_TYPES],
    filterStr: '',
    regex: '',
    tagIds: [],
    limit: 500,
    offset: 0,
  })

  async function fetchTimeline(collectionId) {
    loading.value = true
    error.value = null
    try {
      const params = {
        limit: filters.limit,
        offset: filters.offset,
      }
      if (filters.start) params.start = normaliseDateParam(filters.start)
      if (filters.end) params.end = normaliseDateParam(filters.end)
      if (filters.types.length < ALL_ARTIFACT_TYPES.length) params.types = filters.types.join(',')
      if (filters.filterStr) params.filter = filters.filterStr
      if (filters.regex) params.regex = filters.regex
      if (filters.tagIds.length) params.tag_ids = filters.tagIds.join(',')

      const { data } = await axios.get(`/api/collections/${collectionId}/timeline`, { params })
      events.value = data.events
      total.value = data.total
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function appendTimeline(collectionId) {
    loadingMore.value = true
    try {
      filters.offset += filters.limit
      const params = {
        limit: filters.limit,
        offset: filters.offset,
      }
      if (filters.start) params.start = normaliseDateParam(filters.start)
      if (filters.end) params.end = normaliseDateParam(filters.end)
      if (filters.types.length < ALL_ARTIFACT_TYPES.length) params.types = filters.types.join(',')
      if (filters.filterStr) params.filter = filters.filterStr
      if (filters.regex) params.regex = filters.regex
      if (filters.tagIds.length) params.tag_ids = filters.tagIds.join(',')

      const { data } = await axios.get(`/api/collections/${collectionId}/timeline`, { params })
      events.value.push(...data.events)
    } finally {
      loadingMore.value = false
    }
  }

  async function fetchArtifact(collectionId, type, extraParams = {}) {
    const params = {
      limit: filters.limit,
      offset: filters.offset,
      ...extraParams,
    }
    if (filters.filterStr) params.filter = filters.filterStr
    if (filters.regex) params.regex = filters.regex
    if (filters.tagIds.length) params.tag_ids = filters.tagIds.join(',')
    const { data } = await axios.get(`/api/collections/${collectionId}/${type}`, { params })
    return data
  }

  function resetFilters() {
    filters.start = ''
    filters.end = ''
    filters.types = [...ALL_ARTIFACT_TYPES]
    filters.filterStr = ''
    filters.regex = ''
    filters.tagIds = []
    filters.offset = 0
  }

  return { events, total, loading, loadingMore, error, filters, fetchTimeline, appendTimeline, fetchArtifact, resetFilters }
})
