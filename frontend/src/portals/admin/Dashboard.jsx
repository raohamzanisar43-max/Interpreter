import { Link } from 'react-router-dom'
import { useGet } from '../../shared/hooks'
import { Button, Card, Empty, Progress, Query, StatusBadge } from '../../shared/ui'
import { countdown, fmtDate } from '../../shared/util'

export default function Dashboard() {
  const q = useGet('/admin/dashboard/', { refetchInterval: 30000 })
  return (
    <div className="stack">
      <div className="page-head"><h1>Dashboard</h1><Link className="btn primary" to="/admin/rounds/new">+ New round</Link></div>
      <Query q={q}>{(d) => d.rounds.length === 0 ? (
        <Empty action={<Link className="btn primary" to="/admin/rounds/new">Create your first round</Link>}>No active rounds. {d.drafts ? `${d.drafts} draft(s) waiting.` : ''}</Empty>
      ) : (
        <div className="grid">{d.rounds.map((r) => (
          <Card key={r.id} title={r.name} actions={<StatusBadge status={r.status} />}>
            <p className="muted small">{r.language} · {fmtDate(r.deadline)}{r.status === 'open' && <> · <strong>{countdown(r.deadline)}</strong></>}</p>
            <div className="stack" style={{ gap: 10 }}>
              <div><div className="row between small"><span>Submitted</span><strong>{r.submitted} / {r.assignments_total}</strong></div><Progress value={r.submitted} max={r.assignments_total} /></div>
              {r.rating_total > 0 && <div><div className="row between small"><span>Rating</span><strong>{r.rating_done} / {r.rating_total}</strong></div><Progress value={r.rating_done} max={r.rating_total} /></div>}
              {r.reports_pending > 0 && <span className="badge warn">{r.reports_pending} report(s) pending</span>}
              <Link className="btn" to={`/admin/rounds/${r.id}`}>Open round</Link>
            </div>
          </Card>
        ))}</div>
      )}</Query>
    </div>
  )
}
