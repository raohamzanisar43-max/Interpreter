// Minimal IndexedDB key/value store: keeps un-uploaded recordings until the server confirms them.
const DB = 'eqal'
const STORE = 'takes'

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function tx(mode, fn) {
  try {
    const db = await open()
    return await new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode)
      const r = fn(t.objectStore(STORE))
      t.oncomplete = () => resolve(r?.result)
      t.onerror = () => reject(t.error)
    })
  } catch { return undefined }   // private mode etc.: caching is best-effort
}

export const idbPut = (k, v) => tx('readwrite', (s) => s.put(v, k))
export const idbGet = (k) => tx('readonly', (s) => s.get(k))
export const idbDel = (k) => tx('readwrite', (s) => s.delete(k))
