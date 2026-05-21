<script setup>
import { ref, onMounted } from 'vue'
import { useTagsStore } from '../stores/tags.js'

const tagsStore = useTagsStore()

const editingId  = ref(null)
const editName   = ref('')
const editColor  = ref('')
const deletingId = ref(null)
const newName    = ref('')
const newColor   = ref('gray')
const saving     = ref(false)

const COLORS = ['red', 'orange', 'yellow', 'green', 'teal', 'blue', 'purple', 'pink', 'gray']

const COLOR_DOT = {
  red:    'bg-red-400',
  orange: 'bg-orange-400',
  yellow: 'bg-yellow-400',
  green:  'bg-green-400',
  teal:   'bg-teal-400',
  blue:   'bg-blue-400',
  purple: 'bg-purple-400',
  pink:   'bg-pink-400',
  gray:   'bg-gray-400',
}

const COLOR_BADGE = {
  red:    'bg-red-900/60 text-red-300 border-red-700',
  orange: 'bg-orange-900/60 text-orange-300 border-orange-700',
  yellow: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  green:  'bg-green-900/60 text-green-300 border-green-700',
  teal:   'bg-teal-900/60 text-teal-300 border-teal-700',
  blue:   'bg-blue-900/60 text-blue-300 border-blue-700',
  purple: 'bg-purple-900/60 text-purple-300 border-purple-700',
  pink:   'bg-pink-900/60 text-pink-300 border-pink-700',
  gray:   'bg-gray-700/60 text-gray-300 border-gray-600',
}

onMounted(() => tagsStore.fetchTags())

// ── Create ────────────────────────────────────────────────────────────────────

async function submitCreate() {
  const name = newName.value.trim()
  if (!name || saving.value) return
  saving.value = true
  try {
    await tagsStore.createTag(name, newColor.value)
    newName.value = ''
    newColor.value = 'gray'
  } finally {
    saving.value = false
  }
}

// ── Edit ──────────────────────────────────────────────────────────────────────

function startEdit(tag) {
  deletingId.value = null
  editingId.value = tag.id
  editName.value = tag.name
  editColor.value = tag.color
}

function cancelEdit() {
  editingId.value = null
}

async function submitEdit() {
  const name = editName.value.trim()
  if (!name || saving.value) return
  saving.value = true
  try {
    await tagsStore.updateTag(editingId.value, { name, color: editColor.value })
    editingId.value = null
  } finally {
    saving.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

function startDelete(tag) {
  editingId.value = null
  deletingId.value = tag.id
}

function cancelDelete() {
  deletingId.value = null
}

async function confirmDelete() {
  if (saving.value) return
  saving.value = true
  try {
    await tagsStore.deleteTag(deletingId.value)
    deletingId.value = null
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <h1 class="text-xl font-semibold text-gray-100 mb-6">Tag Manager</h1>

    <!-- Create form -->
    <div class="bg-gray-900 border border-gray-700 rounded-lg p-4 mb-6">
      <label class="text-xs font-semibold text-gray-400 uppercase tracking-wider block mb-3">New tag</label>
      <div class="flex items-center gap-3 flex-wrap">
        <input
          v-model="newName"
          placeholder="Tag name"
          @keydown.enter="submitCreate"
          class="bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 w-48"
        />
        <!-- Color swatches -->
        <div class="flex gap-1.5">
          <button
            v-for="c in COLORS"
            :key="c"
            @click="newColor = c"
            :class="[
              'w-5 h-5 rounded-full transition-all',
              COLOR_DOT[c],
              newColor === c ? 'ring-2 ring-white ring-offset-1 ring-offset-gray-900 scale-110' : 'opacity-60 hover:opacity-90',
            ]"
            :title="c"
          />
        </div>
        <button
          @click="submitCreate"
          :disabled="!newName.trim() || saving"
          class="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-sm text-white transition-colors"
        >Create</button>
      </div>
    </div>

    <!-- Tag list -->
    <div class="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
      <div class="px-4 py-2.5 border-b border-gray-700">
        <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Tags
          <span class="ml-1 text-gray-600 font-normal normal-case">({{ tagsStore.tags.length }})</span>
        </span>
      </div>

      <div v-if="!tagsStore.tags.length" class="px-4 py-8 text-center text-sm text-gray-500">
        No tags yet. Create one above.
      </div>

      <ul v-else class="divide-y divide-gray-800">
        <li v-for="tag in tagsStore.tags" :key="tag.id">

          <!-- Delete confirmation state -->
          <div v-if="deletingId === tag.id" class="px-4 py-3 flex items-center gap-3 bg-red-950/30">
            <span class="text-sm text-red-300 flex-1">
              Delete <span class="font-mono font-medium">"{{ tag.name }}"</span>?
              This removes the tag from all tagged rows.
            </span>
            <button
              @click="confirmDelete"
              :disabled="saving"
              class="px-3 py-1 rounded bg-red-700 hover:bg-red-600 disabled:opacity-40 text-xs text-white"
            >Delete</button>
            <button
              @click="cancelDelete"
              class="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-xs text-gray-300"
            >Cancel</button>
          </div>

          <!-- Edit state -->
          <div v-else-if="editingId === tag.id" class="px-4 py-3 flex items-center gap-3 flex-wrap bg-gray-800/50">
            <input
              v-model="editName"
              @keydown.enter="submitEdit"
              @keydown.esc="cancelEdit"
              class="bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500 w-48"
              autofocus
            />
            <div class="flex gap-1.5">
              <button
                v-for="c in COLORS"
                :key="c"
                @click="editColor = c"
                :class="[
                  'w-5 h-5 rounded-full transition-all',
                  COLOR_DOT[c],
                  editColor === c ? 'ring-2 ring-white ring-offset-1 ring-offset-gray-900 scale-110' : 'opacity-60 hover:opacity-90',
                ]"
                :title="c"
              />
            </div>
            <div class="flex gap-1.5 ml-auto">
              <button
                @click="submitEdit"
                :disabled="!editName.trim() || saving"
                class="px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-xs text-white"
              >Save</button>
              <button
                @click="cancelEdit"
                class="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-xs text-gray-300"
              >Cancel</button>
            </div>
          </div>

          <!-- Normal state -->
          <div v-else class="px-4 py-3 flex items-center gap-3 hover:bg-gray-800/30 transition-colors">
            <span :class="[
              'inline-flex items-center text-xs font-mono px-1.5 py-0.5 rounded border',
              COLOR_BADGE[tag.color] ?? COLOR_BADGE.gray,
            ]">{{ tag.name }}</span>
            <span v-if="tag.is_default" class="text-xs text-gray-600 font-mono">default</span>
            <div class="flex gap-1 ml-auto">
              <button
                @click="startEdit(tag)"
                class="p-1.5 rounded text-gray-500 hover:text-gray-200 hover:bg-gray-700 transition-colors"
                title="Rename / recolor"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                </svg>
              </button>
              <button
                @click="startDelete(tag)"
                class="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-gray-700 transition-colors"
                title="Delete tag"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                </svg>
              </button>
            </div>
          </div>

        </li>
      </ul>
    </div>
  </div>
</template>
