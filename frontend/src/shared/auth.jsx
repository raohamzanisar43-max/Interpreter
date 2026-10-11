import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, refreshSession, setAccessToken, setLogoutHandler } from './api'
import { Spinner } from './ui'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export const HOME = { admin: '/admin', company: '/company', rater: '/rater' }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  const setSession = useCallback((data) => {
    setAccessToken(data.access)
    setUser(data.user)
  }, [])

  const logout = useCallback(async (silent) => {
    try { if (!silent) await api.post('/auth/logout/') } catch { /* ignore */ }
    setAccessToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    setLogoutHandler(() => { setAccessToken(null); setUser(null) })
    refreshSession().then(setSession).catch(() => {}).finally(() => setReady(true))
  }, [setSession])

  // idle timeout (admin / rater): auto-logout after N minutes without input
  const timer = useRef()
  useEffect(() => {
    if (!user || !['admin', 'rater'].includes(user.role)) return undefined
    const ms = (user.idle_timeout_minutes || 30) * 60 * 1000
    const reset = () => { clearTimeout(timer.current); timer.current = setTimeout(() => logout(), ms) }
    const evs = ['mousemove', 'keydown', 'click', 'touchstart']
    evs.forEach((e) => window.addEventListener(e, reset, { passive: true }))
    reset()
    return () => { clearTimeout(timer.current); evs.forEach((e) => window.removeEventListener(e, reset)) }
  }, [user, logout])

  const refreshUser = useCallback(async () => {
    const r = await api.get('/auth/me/')
    setUser(r.data)
  }, [])

  return <Ctx.Provider value={{ user, ready, setSession, logout, refreshUser }}>{children}</Ctx.Provider>
}

export function ProtectedRoute({ role, children }) {
  const { user, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <div className="auth-wrap"><Spinner /></div>
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  if (user.role !== role) return <Navigate to="/403" replace />
  return children
}
