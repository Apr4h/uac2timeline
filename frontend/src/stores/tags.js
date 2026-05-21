import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useTagsStore = defineStore('tags', () => {
  // All available tags in the system
  const tags = ref([])

  // Taggings for the currently loaded collection.
  // Map keyed by `${artifact_type}-${artifact_id}` → array of Tag objects
  const taggings = ref(new Map())

  async function fetchTags() {
    const { data } = await axios.get('/api/tags')
    tags.value = data
  }

  async function fetchCollectionTaggings(collectionId) {
    const { data } = await axios.get(`/api/collections/${collectionId}/taggings`)
    const map = new Map()
    for (const t of data) {
      const key = `${t.artifact_type}-${t.artifact_id}`
      if (!map.has(key)) map.set(key, [])
      const tag = tags.value.find(tg => tg.id === t.tag_id)
      if (tag) map.get(key).push(tag)
    }
    taggings.value = map
  }

  // Returns tags applied to a single row
  function getRowTags(artifactType, artifactId) {
    return taggings.value.get(`${artifactType}-${artifactId}`) ?? []
  }

  // Returns { applied: Set<id>, partial: Set<id> } across a set of rows
  // applied = all selected rows have the tag; partial = only some do
  function getBulkTagState(rows) {
    if (!rows.length) return { applied: new Set(), partial: new Set() }
    const counts = new Map()
    for (const { artifactType, artifactId } of rows) {
      for (const tag of getRowTags(artifactType, artifactId)) {
        counts.set(tag.id, (counts.get(tag.id) ?? 0) + 1)
      }
    }
    const applied = new Set()
    const partial = new Set()
    for (const [tagId, count] of counts) {
      if (count === rows.length) applied.add(tagId)
      else partial.add(tagId)
    }
    return { applied, partial }
  }

  async function applyTag(tagId, artifactType, artifactIds) {
    await axios.post('/api/taggings', { tag_id: tagId, artifact_type: artifactType, artifact_ids: artifactIds })
    // Optimistic local update
    const tag = tags.value.find(t => t.id === tagId)
    if (!tag) return
    for (const id of artifactIds) {
      const key = `${artifactType}-${id}`
      const existing = taggings.value.get(key) ?? []
      if (!existing.find(t => t.id === tagId)) {
        taggings.value.set(key, [...existing, tag])
      }
    }
    taggings.value = new Map(taggings.value)
  }

  async function removeTag(tagId, artifactType, artifactIds) {
    await axios.delete('/api/taggings', { data: { tag_id: tagId, artifact_type: artifactType, artifact_ids: artifactIds } })
    for (const id of artifactIds) {
      const key = `${artifactType}-${id}`
      const existing = taggings.value.get(key) ?? []
      taggings.value.set(key, existing.filter(t => t.id !== tagId))
    }
    taggings.value = new Map(taggings.value)
  }

  async function createTag(name, color) {
    const { data } = await axios.post('/api/tags', { name, color })
    tags.value = [...tags.value, data]
    return data
  }

  async function updateTag(tagId, patch) {
    const { data } = await axios.patch(`/api/tags/${tagId}`, patch)
    tags.value = tags.value.map(t => t.id === tagId ? data : t)
    // Refresh taggings map so badge colors/names update in place
    taggings.value = new Map(
      [...taggings.value].map(([k, v]) => [
        k,
        v.map(t => t.id === tagId ? data : t),
      ])
    )
    return data
  }

  async function deleteTag(tagId) {
    await axios.delete(`/api/tags/${tagId}`)
    tags.value = tags.value.filter(t => t.id !== tagId)
    for (const [key, list] of taggings.value) {
      taggings.value.set(key, list.filter(t => t.id !== tagId))
    }
    taggings.value = new Map(taggings.value)
  }

  function clearCollectionTaggings() {
    taggings.value = new Map()
  }

  return {
    tags,
    taggings,
    fetchTags,
    fetchCollectionTaggings,
    getRowTags,
    getBulkTagState,
    applyTag,
    removeTag,
    createTag,
    updateTag,
    deleteTag,
    clearCollectionTaggings,
  }
})
