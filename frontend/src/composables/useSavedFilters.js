import { ref } from 'vue'

const _key = (collectionId) => `uac_savedfilters_${collectionId}`

export function useSavedFilters() {
  const saved = ref([])

  function load(collectionId) {
    if (!collectionId) { saved.value = []; return }
    try {
      const raw = localStorage.getItem(_key(collectionId))
      saved.value = raw ? JSON.parse(raw) : []
    } catch {
      saved.value = []
    }
  }

  function save(collectionId, name, filtersSnapshot) {
    if (!collectionId || !name.trim()) return
    const entry = {
      id: crypto.randomUUID(),
      name: name.trim(),
      savedAt: new Date().toISOString(),
      filters: {
        ...filtersSnapshot,
        types:  [...(filtersSnapshot.types  ?? [])],
        tagIds: [...(filtersSnapshot.tagIds ?? [])],
      },
    }
    saved.value = [entry, ...saved.value]
    _persist(collectionId)
    return entry
  }

  function remove(collectionId, id) {
    saved.value = saved.value.filter(e => e.id !== id)
    _persist(collectionId)
  }

  function _persist(collectionId) {
    try {
      localStorage.setItem(_key(collectionId), JSON.stringify(saved.value))
    } catch {}
  }

  return { saved, load, save, remove }
}
