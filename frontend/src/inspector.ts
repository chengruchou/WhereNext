import { ref, watch } from 'vue'

// The researcher view: score numbers, weights and pipeline timings. Visitors see the
// bars and sentences without them. ?inspector=1 in the URL turns it on for a link;
// otherwise the last choice in this browser is kept.

const STORAGE_KEY = 'wherenext.inspector'

function initial (): boolean {
  const fromUrl = new URLSearchParams(window.location.search).get('inspector')
  if (fromUrl !== null) return fromUrl !== '0'
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export const inspector = ref(initial())

watch(inspector, on => {
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? '1' : '0')
  } catch {
    // Storage blocked (private window): the switch still works for this page.
  }
})
