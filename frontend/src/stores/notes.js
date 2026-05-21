import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useNotesStore = defineStore('notes', () => {
  // Map keyed by `${artifact_type}-${artifact_id}` → NoteOut object
  const notes = ref(new Map())

  async function fetchCollectionNotes(collectionId) {
    const { data } = await axios.get(`/api/collections/${collectionId}/notes`)
    const map = new Map()
    for (const n of data) {
      map.set(`${n.artifact_type}-${n.artifact_id}`, n)
    }
    notes.value = map
  }

  function getNoteForRow(artifactType, artifactId) {
    return notes.value.get(`${artifactType}-${artifactId}`) ?? null
  }

  // Returns bulk note state across a set of rows.
  // rows: [{ artifactType, artifactId }]
  function getBulkNoteState(rows) {
    if (!rows.length) return { hasAny: false, allSameContent: false, commonContent: '', noteCount: 0 }
    const rowNotes = rows.map(r => getNoteForRow(r.artifactType, r.artifactId))
    const noteCount = rowNotes.filter(n => n !== null).length
    const hasAny = noteCount > 0
    const hasAll = noteCount === rows.length
    const firstContent = rowNotes.find(n => n !== null)?.content ?? ''
    const allSameContent = hasAll && rowNotes.every(n => n.content === firstContent)
    return {
      hasAny,
      allSameContent,
      commonContent: allSameContent ? firstContent : '',
      noteCount,
    }
  }

  async function upsertNote(artifactType, artifactIds, collectionId, content) {
    const { data } = await axios.post('/api/notes', {
      artifact_type: artifactType,
      artifact_ids: artifactIds,
      collection_id: collectionId,
      content,
    })
    const next = new Map(notes.value)
    for (const n of data) {
      next.set(`${n.artifact_type}-${n.artifact_id}`, n)
    }
    notes.value = next
  }

  async function deleteNote(artifactType, artifactIds) {
    await axios.delete('/api/notes', {
      data: { artifact_type: artifactType, artifact_ids: artifactIds },
    })
    const next = new Map(notes.value)
    for (const id of artifactIds) {
      next.delete(`${artifactType}-${id}`)
    }
    notes.value = next
  }

  function clearCollectionNotes() {
    notes.value = new Map()
  }

  return {
    notes,
    fetchCollectionNotes,
    getNoteForRow,
    getBulkNoteState,
    upsertNote,
    deleteNote,
    clearCollectionNotes,
  }
})
