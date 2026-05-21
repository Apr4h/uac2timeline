<script setup>
/**
 * TagPicker — floating popover for applying / removing tags.
 *
 * Props:
 *   appliedIds  Set<number>   — tag IDs applied to ALL selected rows
 *   partialIds  Set<number>   — tag IDs applied to SOME (but not all) selected rows
 *
 * Emits:
 *   apply(tagId)         — user toggled an unapplied / partial tag → apply to all
 *   remove(tagId)        — user toggled a fully-applied tag → remove from all
 *   create(name, color)  — user created a new tag
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTagsStore } from '../stores/tags.js'

const props = defineProps({
  appliedIds: { type: Object, default: () => new Set() },  // Set<number>
  partialIds:  { type: Object, default: () => new Set() },  // Set<number>
})
const emit = defineEmits(['apply', 'remove', 'create', 'close'])

const store = useTagsStore()
const search = ref('')
const creating = ref(false)
const newName  = ref('')
const newColor = ref('gray')

const COLORS = ['red','orange','yellow','green','teal','blue','purple','pink','gray']

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

const filteredTags = computed(() => {
  const q = search.value.toLowerCase()
  return store.tags.filter(t => t.name.toLowerCase().includes(q))
})

function tagState(tag) {
  if (props.appliedIds.has(tag.id)) return 'applied'
  if (props.partialIds.has(tag.id)) return 'partial'
  return 'none'
}

function toggle(tag) {
  const state = tagState(tag)
  if (state === 'applied') emit('remove', tag.id)
  else emit('apply', tag.id)
}

async function submitCreate() {
  const name = newName.value.trim()
  if (!name) return
  const tag = await store.createTag(name, newColor.value)
  emit('create', tag)
  emit('apply', tag.id)
  creating.value = false
  newName.value = ''
  newColor.value = 'gray'
}

// Close on click outside
const el = ref(null)
function onOutsideClick(e) {
  if (el.value && !el.value.contains(e.target)) emit('close')
}
onMounted(() => document.addEventListener('mousedown', onOutsideClick))
onUnmounted(() => document.removeEventListener('mousedown', onOutsideClick))
</script>

<template>
  <div
    ref="el"
    class="absolute z-50 mt-1 w-56 bg-gray-900 border border-gray-700 rounded shadow-xl text-xs"
    @click.stop
  >
    <!-- Search -->
    <div class="p-2 border-b border-gray-700">
      <input
        v-model="search"
        placeholder="Search tags…"
        autofocus
        class="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 placeholder-gray-500 text-xs outline-none focus:border-blue-500"
      />
    </div>

    <!-- Tag list -->
    <ul class="max-h-48 overflow-y-auto py-1">
      <li
        v-for="tag in filteredTags"
        :key="tag.id"
        @click="toggle(tag)"
        class="flex items-center gap-2 px-3 py-1.5 cursor-pointer hover:bg-gray-800 select-none"
      >
        <!-- State indicator -->
        <span class="w-3 h-3 flex items-center justify-center flex-shrink-0 text-blue-400 font-bold">
          <template v-if="tagState(tag) === 'applied'">✓</template>
          <template v-else-if="tagState(tag) === 'partial'">–</template>
        </span>
        <!-- Color dot -->
        <span :class="['w-2 h-2 rounded-full flex-shrink-0', COLOR_DOT[tag.color] ?? 'bg-gray-400']" />
        <span class="text-gray-200 truncate flex-1">{{ tag.name }}</span>
      </li>
      <li v-if="!filteredTags.length" class="px-3 py-2 text-gray-500 italic">No tags found</li>
    </ul>

    <!-- Create new tag -->
    <div class="border-t border-gray-700">
      <template v-if="!creating">
        <button
          @click="creating = true"
          class="w-full text-left px-3 py-1.5 text-blue-400 hover:bg-gray-800 flex items-center gap-2"
        >
          <span class="text-sm leading-none">+</span> New tag
        </button>
      </template>
      <template v-else>
        <div class="p-2 flex flex-col gap-2">
          <input
            v-model="newName"
            placeholder="Tag name"
            @keydown.enter="submitCreate"
            @keydown.esc="creating = false"
            class="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 placeholder-gray-500 text-xs outline-none focus:border-blue-500"
          />
          <!-- Color swatches -->
          <div class="flex gap-1 flex-wrap">
            <button
              v-for="c in COLORS"
              :key="c"
              @click="newColor = c"
              :class="[
                'w-4 h-4 rounded-full',
                COLOR_DOT[c],
                newColor === c ? 'ring-2 ring-white ring-offset-1 ring-offset-gray-900' : '',
              ]"
              :title="c"
            />
          </div>
          <div class="flex gap-1">
            <button
              @click="submitCreate"
              class="flex-1 px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs"
            >Create</button>
            <button
              @click="creating = false"
              class="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs"
            >Cancel</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
