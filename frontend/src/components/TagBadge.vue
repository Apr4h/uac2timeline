<script setup>
defineProps({
  tag: { type: Object, required: true },
  removable: { type: Boolean, default: false },
})
defineEmits(['remove'])

const COLOR_CLASSES = {
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
</script>

<template>
  <span
    :class="[
      'inline-flex items-center gap-1 text-xs font-mono px-1.5 py-0.5 rounded border',
      COLOR_CLASSES[tag.color] ?? COLOR_CLASSES.gray,
    ]"
  >
    {{ tag.name }}
    <button
      v-if="removable"
      @click.stop="$emit('remove', tag)"
      class="ml-0.5 opacity-60 hover:opacity-100 leading-none"
      title="Remove tag"
    >×</button>
  </span>
</template>
