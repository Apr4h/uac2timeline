<script setup lang="ts">
import { ref, watchEffect, onMounted, onBeforeUnmount } from 'vue'
import { useThemeStore } from './stores/theme'

const theme = useThemeStore()

watchEffect(() => {
  document.documentElement.dataset.flavor = theme.flavor
  document.documentElement.dataset.accent = theme.accent
})

const showPicker = ref(false)

// Close the picker on any document click (the picker itself stops propagation)
function onDocClick() { showPicker.value = false }
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

const FLAVORS = [
  { id: 'night', label: 'Night' },
  { id: 'storm', label: 'Storm' },
  { id: 'light', label: 'Light' },
] as const

// Fixed preview colors so the dots look consistent regardless of active theme
const ACCENTS = [
  { id: 'blue',   color: '#7aa2f7', label: 'Blue'   },
  { id: 'cyan',   color: '#7dcfff', label: 'Cyan'   },
  { id: 'purple', color: '#bb9af7', label: 'Purple' },
  { id: 'green',  color: '#9ece6a', label: 'Green'  },
] as const
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

      <!-- Condensed theme picker -->
      <div class="ml-auto relative" @click.stop>

        <!-- Trigger button: accent dot + current flavor name + chevron -->
        <button
          @click="showPicker = !showPicker"
          class="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-tn-fg-dim hover:text-tn-fg hover:bg-tn-hover transition-colors select-none"
          title="Theme settings"
        >
          <span
            class="w-2.5 h-2.5 rounded-full shrink-0"
            :style="{ background: 'var(--accent)' }"
          />
          <span class="capitalize">{{ theme.flavor }}</span>
          <svg class="w-3 h-3 opacity-50 transition-transform" :class="{ 'rotate-180': showPicker }"
            viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clip-rule="evenodd"/>
          </svg>
        </button>

        <!-- Dropdown panel -->
        <Transition name="picker-drop">
          <div
            v-if="showPicker"
            class="absolute top-full right-0 mt-1.5 w-44 bg-tn-surface border border-tn-border rounded-lg shadow-xl p-3 flex flex-col gap-3 z-50"
          >
            <!-- Flavor row -->
            <div>
              <div class="text-[10px] text-tn-muted uppercase tracking-widest mb-1.5 font-semibold">Theme</div>
              <div class="flex gap-1">
                <button
                  v-for="f in FLAVORS" :key="f.id"
                  @click="theme.setFlavor(f.id)"
                  :class="['flex-1 py-1 rounded text-xs transition-colors',
                    theme.flavor === f.id
                      ? 'bg-tn-accent text-tn-bg font-semibold'
                      : 'bg-tn-raised text-tn-fg-dim hover:bg-tn-hover']"
                >{{ f.label }}</button>
              </div>
            </div>

            <!-- Accent row -->
            <div>
              <div class="text-[10px] text-tn-muted uppercase tracking-widest mb-1.5 font-semibold">Accent</div>
              <div class="flex gap-2">
                <button
                  v-for="a in ACCENTS" :key="a.id"
                  @click="theme.setAccent(a.id)"
                  :title="a.label"
                  class="w-6 h-6 rounded-full transition-all border-2"
                  :style="{ background: a.color }"
                  :class="theme.accent === a.id
                    ? 'border-tn-fg scale-110 shadow-sm'
                    : 'border-transparent hover:border-tn-fg-dim'"
                />
              </div>
            </div>
          </div>
        </Transition>

      </div>
    </header>

    <main class="flex-1">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.picker-drop-enter-active,
.picker-drop-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.picker-drop-enter-from,
.picker-drop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
