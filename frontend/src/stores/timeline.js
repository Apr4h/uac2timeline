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
    colFilters: [],   // [{ col, mode: 'inc'|'exc', pattern, isRegex }]
    tagIds: [],
    limit: 500,
    offset: 0,
  })

  function _buildParams(extra = {}) {
    const params = { limit: filters.limit, offset: filters.offset, ...extra }
    if (filters.start) params.start = normaliseDateParam(filters.start)
    if (filters.end) params.end = normaliseDateParam(filters.end)
    if (filters.tagIds.length) params.tag_ids = filters.tagIds.join(',')
    const activeRules = filters.colFilters.filter(r => r.col && r.pattern)
    if (activeRules.length) params.col_filters = JSON.stringify(activeRules)
    return params
  }

  async function fetchTimeline(collectionId) {
    loading.value = true
    error.value = null
    try {
      const params = _buildParams()
      if (filters.types.length < ALL_ARTIFACT_TYPES.length) params.types = filters.types.join(',')
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
      const params = _buildParams()
      if (filters.types.length < ALL_ARTIFACT_TYPES.length) params.types = filters.types.join(',')
      const { data } = await axios.get(`/api/collections/${collectionId}/timeline`, { params })
      events.value.push(...data.events)
    } finally {
      loadingMore.value = false
    }
  }

  async function fetchArtifact(collectionId, type, extraParams = {}) {
    const params = _buildParams(extraParams)
    const { data } = await axios.get(`/api/collections/${collectionId}/${type}`, { params })
    return data
  }

  function resetFilters() {
    filters.start = ''
    filters.end = ''
    filters.types = [...ALL_ARTIFACT_TYPES]
    filters.colFilters = []
    filters.tagIds = []
    filters.offset = 0
  }

  return { events, total, loading, loadingMore, error, filters, fetchTimeline, appendTimeline, fetchArtifact, resetFilters }
})
