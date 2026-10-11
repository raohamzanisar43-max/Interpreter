import { useState } from 'react'
import { Link, Route, Routes, useParams } from 'react-router-dom'
import { api, download, fieldErrors } from '../../shared/api'
import { useAuth } from '../../shared/auth'
import { LineChart } from '../../shared/Charts'
import PortalLayout from '../../shared/Layout'
import ReportView from '../../shared/ReportView'
import { ErrorPage } from '../../shared/pages'
import { useAction, useGet } from '../../shared/hooks'
import { Badge, Button, Card, Empty, Modal, Progress, Query, StatusBadge, Table, TextInput, useToast } from '../../shared/ui'
import { countdown, fmtDate, mdToHtml, ordinal } from '../../shared/util'

const LINKS = [
  { to: '/company', label: 'Dashboard', end: true }, { to: '/company/interpreters', label: 'Interpreters' }, { to: '/company/rounds', label: 'Rounds' },
  { to: '/company/reports', label: 'Reports' }, { to: '/company/history', label: 'History & trend' },
]

function TermsGate() {
  const q = useGet('/company/terms/')
  const { refreshUser } = useAuth()
  const [ok, setOk] = useState(false)
  const accept = useAction(async (v) => api.post('/company/terms/accept/', { version: v }), { success: 'Thank you — terms accepted.', onSuccess: () => refreshUser() })
  return (
    <main className="auth-wrap">
      <div className="card" style={{ width: 'min(760px, 100%)' }}>
        <div className="brand" style={{ padding: 0 }}>EQAL</div>
        <h1>Please accept the terms to continue</h1>
        <Query q={q}>{(t) => (<>
          <div style={{ maxHeight: '45vh', overflow: 'auto', border: '1px solid var(--border)', borderRadius: 8, padding: '0 14px' }} tabIndex={0} aria-label="Terms text" dangerouslySetInnerHTML={{ __html: mdToHtml(t.body) }} />
          <p className="small muted">Version {t.version}. Your acceptance (version, time and IP address) is recorded. See also our <Link to="/privacy" target="_blank">privacy notice</Link>.</p>
          <label className="row" style={{ margin: '10px 0' }}><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> I have read and accept these terms on behalf of my company.</label>
          <Button variant="primary" disabled={!ok || accept.isPending} onClick={() => accept.mutate(t.version)}>Accept and continue</Button>
        </>)}</Query>
      </div>
    </main>
  )
}

function Dashboard() {
  const rounds = useGet('/company/rounds/')
  const reports = useGet('/company/reports/')
  return (
    <div className="stack">
      <h1>Dashboard</h1>
      <Query q={rounds}>{(rs) => {
        const current = rs.filter((r) => r.status === 'open')
        return (
          <div className="grid">
            <Card title="Current round">{current.length ? current.map((r) => (
              <div key={r.id} className="stack" style={{ gap: 8 }}><strong>{r.name}</strong><span className="muted small">{r.language} · {fmtDate(r.deadline)} · {countdown(r.deadline)}</span>
                <div className="row between small"><span>Interpreters submitted</span><strong>{r.interpreters_submitted}/{r.interpreters_total}</strong></div><Progress value={r.interpreters_submitted} max={r.interpreters_total} />
                <Link className="btn" to={`/company/rounds/${r.id}`}>Details</Link></div>)) : <p className="muted">No round is open right now.</p>}</Card>
            <Card title="Upcoming & past"><Table empty="No rounds yet." rows={rs.slice(0, 5)} columns={[{ label: 'Round', render: (r) => <Link to={`/company/rounds/${r.id}`}>{r.name}</Link> }, { label: 'Deadline', render: (r) => fmtDate(r.deadline) }, { label: '', render: (r) => <StatusBadge status={r.status} /> }]} /></Card>
          </div>)
      }}</Query>
      <Card title="Latest released report"><Query q={reports}>{(rows) => rows.length ? (
        <div className="row between"><div><strong>{rows[0].round_name}</strong><div className="muted small">Released {fmtDate(rows[0].released_at)}</div></div>
          <div className="row"><span className="stat">{rows[0].overall_score}%</span>{rows[0].ranking_visible && <Badge tone="info">{ordinal(rows[0].rank)} of {rows[0].companies_count}</Badge>}<Link className="btn primary" to={`/company/reports/${rows[0].id}`}>View report</Link></div></div>
      ) : <p className="muted">No reports released yet.</p>}</Query></Card>
    </div>
  )
}

function Interpreters() {
  const q = useGet('/company/interpreters/')
  const { confirm, toast } = useToast()
  const [edit, setEdit] = useState(null)
  const [errs, setErrs] = useState({})
  const save = useAction(async (f) => (f.id ? api.patch(`/company/interpreters/${f.id}/`, { full_name: f.full_name, email: f.email }) : api.post('/company/interpreters/', { full_name: f.full_name, email: f.email })),
    { invalidate: ['/company/interpreters/'], success: 'Saved.', onSuccess: () => setEdit(null) })
  const submit = async (e) => { e.preventDefault(); setErrs({}); try { await save.mutateAsync(edit) } catch (er) { setErrs(fieldErrors(er)) } }
  return (
    <div className="stack">
      <div className="page-head"><h1>Interpreters</h1><Button variant="primary" onClick={() => { setErrs({}); setEdit({ full_name: '', email: '' }) }}>+ Add interpreter</Button></div>
      <p className="muted">Interpreters receive a personal secure link by email when a round opens (or when you add them during an open round).</p>
      <Query q={q}>{(rows) => <Table empty="No interpreters yet." rows={rows} columns={[{ label: 'Name', key: 'full_name' }, { label: 'Email', key: 'email' }, { label: 'Status', render: (i) => <StatusBadge status={i.is_active ? 'active' : 'inactive'} /> },
        { label: '', render: (i) => <div className="row"><Button size="sm" onClick={() => { setErrs({}); setEdit(i) }}>Edit</Button>
          <Button size="sm" onClick={async () => { const d = (await api.post(`/company/interpreters/${i.id}/resend/`)).data; toast(d.sent ? 'Link re-sent.' : 'No open round to send a link for.') }}>Resend link</Button>
          <Button size="sm" onClick={async () => { if (i.is_active && !(await confirm({ message: `Deactivate ${i.full_name}?` }))) return; await api.patch(`/company/interpreters/${i.id}/`, { is_active: !i.is_active }); q.refetch() }}>{i.is_active ? 'Deactivate' : 'Activate'}</Button></div> }]} />}</Query>
      {edit && <Modal title={edit.id ? 'Edit interpreter' : 'Add interpreter'} onClose={() => setEdit(null)}><form onSubmit={submit}>
        <TextInput label="Full name" required value={edit.full_name} error={errs.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} />
        <TextInput label="Email" type="email" required value={edit.email} error={errs.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" type="submit">Save</Button></div></form></Modal>}
    </div>
  )
}

function Rounds() {
  const q = useGet('/company/rounds/')
  return (
    <div className="stack"><h1>Rounds</h1>
      <Query q={q}>{(rows) => <Table empty="Your company has not been invited to a round yet." rows={rows} columns={[{ label: 'Round', render: (r) => <Link to={`/company/rounds/${r.id}`}><strong>{r.name}</strong></Link> }, { label: 'Language', key: 'language' }, { label: 'Deadline', render: (r) => fmtDate(r.deadline) }, { label: 'Status', render: (r) => <StatusBadge status={r.status} /> }, { label: 'Submitted', render: (r) => `${r.interpreters_submitted}/${r.interpreters_total}` }]} />}</Query></div>
  )
}

function RoundDetail() {
  const { id } = useParams()
  const q = useGet(`/company/rounds/${id}/progress/`, { refetchInterval: 30000 })
  return (
    <div className="stack">
      <Link to="/company/rounds" className="small">← Rounds</Link>
      <Query q={q}>{(r) => (<>
        <div className="page-head"><h1 style={{ margin: 0 }}>{r.name} <StatusBadge status={r.status} /></h1></div>
        <Card title="Round info"><p>{r.language} · deadline <strong>{fmtDate(r.deadline)}</strong> {r.status === 'open' && `(${countdown(r.deadline)})`}</p><p className="muted" style={{ whiteSpace: 'pre-wrap' }}>{r.instructions}</p>
          <div className="row between small"><span>Interpreters submitted</span><strong>{r.interpreters_submitted}/{r.interpreters_total}</strong></div><Progress value={r.interpreters_submitted} max={r.interpreters_total} /></Card>
        <Card title="Interpreters"><Table empty="No interpreters." rows={r.interpreters.map((i, k) => ({ ...i, id: k }))} columns={[{ label: 'Interpreter', key: 'name' }, { label: 'Status', render: (i) => <Badge tone={i.submitted ? 'ok' : 'warn'}>{i.submitted ? 'Done' : 'Not done'}</Badge> }, { label: 'Submitted at', render: (i) => fmtDate(i.submitted_at) }]} /></Card>
      </>)}</Query>
    </div>
  )
}

function Reports() {
  const q = useGet('/company/reports/')
  return (
    <div className="stack"><h1>Reports</h1>
      <Query q={q}>{(rows) => rows.length === 0 ? <Empty>No reports have been released to you yet.</Empty> : <Table rows={rows} columns={[{ label: 'Round', render: (r) => <Link to={`/company/reports/${r.id}`}><strong>{r.round_name}</strong></Link> }, { label: 'Released', render: (r) => fmtDate(r.released_at) }, { label: 'Score', render: (r) => `${r.overall_score}%` }, { label: 'Rank', render: (r) => (r.ranking_visible ? `${ordinal(r.rank)} of ${r.companies_count}` : '—') }]} />}</Query></div>
  )
}

function Report() {
  const { id } = useParams()
  const q = useGet(`/company/reports/${id}/`)
  const { toast } = useToast()
  return (
    <div className="stack">
      <Link to="/company/reports" className="small">← Reports</Link>
      <Query q={q}>{(d) => (<>
        <div className="page-head"><div><h1 style={{ marginBottom: 0 }}>{d.round_name}</h1><span className="muted small">{d.language} · released {fmtDate(d.released_at)}</span></div>
          <Button variant="primary" onClick={() => download(`/company/reports/${id}/pdf/`, `eqal-report-${id}.pdf`).catch(toast.error)}>Download PDF</Button></div>
        <ReportView data={d.data} summary={d.summary} />
      </>)}</Query>
    </div>
  )
}

function History() {
  const q = useGet('/company/history/')
  return (
    <div className="stack"><h1>History & trend</h1>
      <Query q={q}>{(rows) => rows.length === 0 ? <Empty>History appears after your first released report.</Empty> : (<div className="grid2">
        <Card title="Score across rounds"><LineChart points={rows.map((r) => ({ label: r.round, value: r.score }))} /></Card>
        <Card title="Rank over time">{rows.some((r) => r.rank) ? <LineChart invert max={Math.max(...rows.map((r) => r.companies_count || 3), 3)} unit="" points={rows.map((r) => ({ label: r.round, value: r.rank }))} /> : <p className="muted">Ranking was not shown for these rounds.</p>}</Card>
      </div>)}</Query></div>
  )
}

export default function CompanyApp() {
  const { user } = useAuth()
  if (user?.company?.terms_required) return <TermsGate />
  return (
    <PortalLayout title={user?.company?.name || 'Company'} links={LINKS}>
      <Routes>
        <Route index element={<Dashboard />} /><Route path="interpreters" element={<Interpreters />} />
        <Route path="rounds" element={<Rounds />} /><Route path="rounds/:id" element={<RoundDetail />} />
        <Route path="reports" element={<Reports />} /><Route path="reports/:id" element={<Report />} />
        <Route path="history" element={<History />} /><Route path="*" element={<ErrorPage code={404} />} />
      </Routes>
    </PortalLayout>
  )
}
