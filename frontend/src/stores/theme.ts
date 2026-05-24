import { defineStore } from 'pinia'

export type Flavor = 'night' | 'storm' | 'light'
export type Accent = 'blue' | 'cyan' | 'purple' | 'green'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    flavor: (localStorage.getItem('tn-flavor') as Flavor) || 'night',
    accent: (localStorage.getItem('tn-accent') as Accent) || 'blue',
  }),
  actions: {
    setFlavor(f: Flavor) { this.flavor = f; localStorage.setItem('tn-flavor', f) },
    setAccent(a: Accent) { this.accent = a; localStorage.setItem('tn-accent', a) },
  },
})