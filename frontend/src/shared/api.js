import axios from 'axios'

let accessToken = null
let onLogout = () => {}
let refreshing = null

export const setAccessToken = (t) => { accessToken = t }
export const setLogoutHandler = (fn) => { onLogout = fn }

export const api = axios.create({ baseURL: '/api', withCredentials: true })

api.interceptors.request.use((cfg) => {
  if (accessToken) cfg.headers.Authorization = `Bearer ${accessToken}`
  return cfg
})

export async function refreshSession() {
  if (!refreshing) {
    refreshing = axios.post('/api/auth/refresh/', null, { withCredentials: true })
      .then((r) => { accessToken = r.data.access; return r.data })
      .finally(() => { refreshing = null })
  }
  return refreshing
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error
    const isAuthCall = config?.url?.startsWith('/auth/')
    if (response?.status === 401 && !config._retry && !isAuthCall && accessToken) {
      config._retry = true
      try {
        await refreshSession()
        config.headers.Authorization = `Bearer ${accessToken}`
        return api(config)
      } catch {
        accessToken = null
        onLogout()
      }
    }
    return Promise.reject(error)
  },
)

// ---- interpreter secure-link client (separate from the JWT client)
const TOKEN_KEY = 'eqal_assignment_token'
export const getLinkToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
export const setLinkToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } }

export const iapi = axios.create({ baseURL: '/api' })
iapi.interceptors.request.use((cfg) => {
  const t = getLinkToken()
  if (t) cfg.headers['X-Assignment-Token'] = t
  return cfg
})

/** Human readable message from the {code, message, fields} error format. */
export function errMsg(e) {
  const d = e?.response?.data
  if (!d) return e?.message || 'Something went wrong.'
  const fields = d.fields && Object.entries(d.fields).map(([k, v]) => `${k}: ${[].concat(v).join(' ')}`).join(' · ')
  if (d.message && d.message !== 'Validation failed.') return d.message
  return fields || d.message || 'Request failed.'
}
export const fieldErrors = (e) => e?.response?.data?.fields || {}
export const errCode = (e) => e?.response?.data?.code

export async function download(url, filename) {
  const r = await api.get(url, { responseType: 'blob' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
