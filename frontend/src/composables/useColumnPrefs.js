import { reactive } from 'vue'

const STORAGE_KEY = 'uac_colprefs'

function load(tab) {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY}_${tab}`)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function save(tab, prefs) {
  try {
    localStorage.setItem(`${STORAGE_KEY}_${tab}`, JSON.stringify(prefs))
  } catch {}
}

export function useColumnPrefs(colDefaults) {
  const state = reactive({})

  for (const tab of Object.keys(colDefaults)) {
    const defaults = colDefaults[tab]
    const saved = load(tab)
    if (saved?.order) {
      const savedSet = new Set(saved.order)
      const order = [
        ...saved.order.filter(c => defaults.includes(c)),
        ...defaults.filter(c => !savedSet.has(c)),
      ]
      state[tab] = { order, widths: saved.widths ?? {} }
    } else {
      state[tab] = { order: [...defaults], widths: {} }
    }
  }

  function getOrder(tab) {
    return state[tab]?.order ?? colDefaults[tab] ?? []
  }

  function getWidths(tab) {
    return state[tab]?.widths ?? {}
  }

  function setWidth(tab, col, px) {
    if (!state[tab]) return
    state[tab].widths[col] = Math.max(40, Math.round(px))
    save(tab, state[tab])
  }

  function reorder(tab, fromIdx, toIdx) {
    if (fromIdx === toIdx || !state[tab]) return
    const cols = [...state[tab].order]
    const [moved] = cols.splice(fromIdx, 1)
    cols.splice(toIdx, 0, moved)
    state[tab].order = cols
    save(tab, state[tab])
  }

  function reset(tab) {
    state[tab] = { order: [...(colDefaults[tab] ?? [])], widths: {} }
    try { localStorage.removeItem(`${STORAGE_KEY}_${tab}`) } catch {}
  }

  return { getOrder, getWidths, setWidth, reorder, reset }
}
