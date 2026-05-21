<script setup lang="ts">
import { watchEffect } from 'vue'
import { useThemeStore } from './stores/theme'
const theme = useThemeStore()

watchEffect(() => {
  document.documentElement.dataset.flavor = theme.flavor
  document.documentElement.dataset.accent = theme.accent
})
</script>

<template>
  <div class="min-h-screen bg-tn-bg text-tn-fg flex flex-col">
    <header class="bg-tn-surface border-b border-tn-border px-6 py-3 flex items-center gap-4">
      <router-link to="/collections" class="text-lg font-semibold text-tn-accent hover:text-tn-accent-hover">
        uac2timeline
      </router-link>
      <nav class="flex gap-4 text-sm text-tn-fg-dim">
        <router-link to="/collections" class="hover:text-tn-fg" active-class="text-tn-fg">Collections</router-link>
        <router-link to="/tags" class="hover:text-tn-fg" active-class="text-tn-fg">Tags</router-link>
      </nav>
      <div class="ml-auto flex items-center gap-1 text-xs text-tn-muted">
        <button @click="theme.setFlavor('night')"  :class="theme.flavor === 'night'  ? 'text-tn-fg bg-tn-hover' : 'hover:text-tn-fg-dim'" class="px-2 py-1 rounded">Night</button>
        <button @click="theme.setFlavor('storm')"  :class="theme.flavor === 'storm'  ? 'text-tn-fg bg-tn-hover' : 'hover:text-tn-fg-dim'" class="px-2 py-1 rounded">Storm</button>
        <span class="mx-1 text-tn-border">|</span>
        <button @click="theme.setAccent('blue')"   :class="theme.accent === 'blue'   ? 'text-tn-fg bg-tn-hover' : 'hover:text-tn-fg-dim'" class="px-2 py-1 rounded">Blue</button>
        <button @click="theme.setAccent('cyan')"   :class="theme.accent === 'cyan'   ? 'text-tn-fg bg-tn-hover' : 'hover:text-tn-fg-dim'" class="px-2 py-1 rounded">Cyan</button>
        <button @click="theme.setAccent('purple')" :class="theme.accent === 'purple' ? 'text-tn-fg bg-tn-hover' : 'hover:text-tn-fg-dim'" class="px-2 py-1 rounded">Purple</button>
        <button @click="theme.setAccent('green')"  :class="theme.accent === 'green'  ? 'text-tn-fg bg-tn-hover' : 'hover:text-tn-fg-dim'" class="px-2 py-1 rounded">Green</button>
      </div>
    </header>
    <main class="flex-1">
      <router-view />
    </main>
  </div>
</template>
