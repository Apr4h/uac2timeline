<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTagsStore } from '../stores/tags.js'

const props = defineProps({
  appliedIds: { type: Object, default: () => new Set() },
  partialIds:  { type: Object, default: () => new Set() },
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
    class="absolute z-50 mt-1 w-56 bg-tn-surface border border-tn-border rounded shadow-xl text-xs"
    @click.stop
  >
    <!-- Search -->
    <div class="p-2 border-b border-tn-border">
      <input
        v-model="search"
        placeholder="Search tags…"
        autofocus
        class="w-full bg-tn-raised border border-tn-border-strong rounded px-2 py-1 text-tn-fg placeholder-tn-muted text-xs outline-none focus:border-tn-accent"
      />
    </div>

    <!-- Tag list -->
    <ul class="max-h-48 overflow-y-auto py-1">
      <li
        v-for="tag in filteredTags"
        :key="tag.id"
        @click="toggle(tag)"
        class="flex items-center gap-2 px-3 py-1.5 cursor-pointer hover:bg-tn-raised select-none"
      >
        <span class="w-3 h-3 flex items-center justify-center flex-shrink-0 text-tn-accent font-bold">
          <template v-if="tagState(tag) === 'applied'">✓</template>
          <template v-else-if="tagState(tag) === 'partial'">–</template>
        </span>
        <span :class="['w-2 h-2 rounded-full flex-shrink-0', COLOR_DOT[tag.color] ?? 'bg-gray-400']" />
        <span class="text-tn-fg truncate flex-1">{{ tag.name }}</span>
      </li>
      <li v-if="!filteredTags.length" class="px-3 py-2 text-tn-muted italic">No tags found</li>
    </ul>

    <!-- Create new tag -->
    <div class="border-t border-tn-border">
      <template v-if="!creating">
        <button
          @click="creating = true"
          class="w-full text-left px-3 py-1.5 text-tn-accent hover:bg-tn-raised flex items-center gap-2"
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
            class="w-full bg-tn-raised border border-tn-border-strong rounded px-2 py-1 text-tn-fg placeholder-tn-muted text-xs outline-none focus:border-tn-accent"
          />
          <div class="flex gap-1 flex-wrap">
            <button
              v-for="c in COLORS"
              :key="c"
              @click="newColor = c"
              :class="[
                'w-4 h-4 rounded-full',
                COLOR_DOT[c],
                newColor === c ? 'ring-2 ring-white ring-offset-1 ring-offset-tn-surface' : '',
              ]"
              :title="c"
            />
          </div>
          <div class="flex gap-1">
            <button
              @click="submitCreate"
              class="flex-1 px-2 py-1 bg-tn-accent hover:bg-tn-accent-hover text-tn-bg rounded text-xs"
            >Create</button>
            <button
              @click="creating = false"
              class="px-2 py-1 bg-tn-hover hover:bg-tn-border-strong text-tn-fg-dim rounded text-xs"
            >Cancel</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
