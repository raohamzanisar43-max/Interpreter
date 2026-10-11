import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { errMsg } from './api'

export const Spinner = () => <span className="spinner" role="status" aria-label="Loading" />

export function Skeleton({ rows = 4 }) {
  return <div aria-busy="true" aria-label="Loading">{Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ width: `${95 - i * 9}%` }} />)}</div>
}

export function Empty({ children, action }) {
  return <div className="empty"><p>{children}</p>{action}</div>
}

export function Badge({ tone, children }) {
  return <span className={`badge ${tone || ''}`}>{children}</span>
}

const STATUS_TONE = {
  draft: '', open: 'info', closed: 'warn', rating: 'info', review: 'warn', released: 'ok', archived: '',
  not_started: '', in_progress: 'warn', submitted: 'ok', approved: 'info', todo: '', done: 'ok', active: 'ok', inactive: 'bad',
}
export const StatusBadge = ({ status }) => <Badge tone={STATUS_TONE[status]}>{String(status).replace('_', ' ')}</Badge>

export const Button = ({ variant, size, className = '', ...p }) => (
  <button type="button" className={`btn ${variant || ''} ${size || ''} ${className}`} {...p} />
)

export const Card = ({ title, actions, children, className = '' }) => (
  <section className={`card ${className}`}>
    {(title || actions) && <div className="row between" style={{ marginBottom: 10 }}>{title && <h2 style={{ margin: 0 }}>{title}</h2>}<div className="row">{actions}</div></div>}
    {children}
  </section>
)

export function Field({ label, error, hint, children, id }) {
  const fid = id || `f-${String(label).replace(/\W+/g, '-')}`
  return (
    <div className="field">
      {label && <label htmlFor={fid}>{label}</label>}
      {typeof children === 'function' ? children(fid) : children}
      {hint && <span className="muted small">{hint}</span>}
      {error && <span className="err" role="alert">{[].concat(error).join(' ')}</span>}
    </div>
  )
}

export const TextInput = ({ label, error, hint, ...p }) => (
  <Field label={label} error={error} hint={hint}>{(id) => <input id={id} {...p} />}</Field>
)

export function Modal({ title, onClose, children, wide, actions }) {
  const ref = useRef()
  useEffect(() => {
    const prev = document.activeElement
    ref.current?.querySelector('input, select, textarea, button')?.focus()
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.() }
  }, [onClose])
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <h2>{title}</h2>
        {children}
        {actions && <div className="actions">{actions}</div>}
      </div>
    </div>
  )
}

export function Table({ columns, rows, empty = 'Nothing here yet.', rowClass, onRow }) {
  if (!rows?.length) return <Empty>{empty}</Empty>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((c) => <th key={c.key || c.label}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className={rowClass?.(r) || ''} onClick={onRow ? () => onRow(r) : undefined} style={onRow ? { cursor: 'pointer' } : undefined}>
              {columns.map((c) => <td key={c.key || c.label}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className={value === t.key ? 'active' : ''} onClick={() => onChange(t.key)}>{t.label}</button>
      ))}
    </div>
  )
}

export const Progress = ({ value, max }) => (
  <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
    <div style={{ width: `${max ? Math.min(100, (value / max) * 100) : 0}%` }} />
  </div>
)

/** Shows loading skeleton / error / content for a react-query result. */
export function Query({ q, children, skeleton }) {
  if (q.isLoading) return skeleton || <Skeleton />
  if (q.isError) return <div className="alert bad" role="alert">{errMsg(q.error)} <Button size="sm" onClick={() => q.refetch()}>Retry</Button></div>
  return children(q.data)
}

// ---------- toasts + confirm
const ToastCtx = createContext(null)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const [confirmState, setConfirm] = useState(null)
  const push = useCallback((msg, tone) => {
    const id = Math.random()
    setItems((x) => [...x, { id, msg, tone }])
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 4500)
  }, [])
  const toast = useCallback((m) => push(m, 'ok'), [push])
  toast.error = (e) => push(typeof e === 'string' ? e : errMsg(e), 'bad')
  toast.info = (m) => push(m)
  const confirm = useCallback((opts) => new Promise((resolve) => setConfirm({ ...(typeof opts === 'string' ? { message: opts } : opts), resolve })), [])
  const done = (v) => { confirmState.resolve(v); setConfirm(null) }
  return (
    <ToastCtx.Provider value={{ toast, confirm }}>
      {children}
      <div className="toasts" aria-live="polite">{items.map((i) => <div key={i.id} className={`toast ${i.tone || ''}`}>{i.msg}</div>)}</div>
      {confirmState && (
        <Modal title={confirmState.title || 'Are you sure?'} onClose={() => done(false)}
          actions={<><Button onClick={() => done(false)}>Cancel</Button><Button variant={confirmState.danger ? 'danger' : 'primary'} onClick={() => done(true)}>{confirmState.confirmLabel || 'Confirm'}</Button></>}>
          <p>{confirmState.message}</p>
        </Modal>
      )}
    </ToastCtx.Provider>
  )
}

export function usePersistentState(key, initial) {
  const [v, setV] = useState(() => { try { return JSON.parse(localStorage.getItem(key)) ?? initial } catch { return initial } })
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* ignore */ } }, [key, v])
  return [v, setV]
}
