import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from './auth'
import { Button } from './ui'

export default function PortalLayout({ title, links, children }) {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  return (
    <div className="shell">
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
        <div className="brand">EQAL<small>{title}</small></div>
        <nav className="nav" onClick={() => setOpen(false)}>
          {links.map((l) => <NavLink key={l.to} to={l.to} end={l.end}>{l.label}</NavLink>)}
        </nav>
        <div className="spacer" />
        <div className="small muted" style={{ padding: '6px 10px', wordBreak: 'break-all' }}>{user?.email}{user?.company ? <><br />{user.company.name}</> : null}</div>
        <Button onClick={() => logout()}>Sign out</Button>
      </aside>
      <div>
        <div className="topbar">
          <Button size="sm" onClick={() => setOpen(!open)} aria-label="Toggle menu" aria-expanded={open}>☰</Button>
          <strong style={{ color: 'var(--primary)' }}>EQAL</strong><span className="muted small">{title}</span>
        </div>
        <main className="main" id="content">{children || <Outlet />}</main>
      </div>
    </div>
  )
}
