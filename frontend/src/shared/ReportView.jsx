import { BarList } from './Charts'
import { Card } from './ui'
import { ordinal } from './util'

/** Exactly what a company sees (admin preview uses the same component). */
export default function ReportView({ data, summary }) {
  if (!data) return null
  return (
    <div className="stack">
      <div className="grid">
        <Card title="Overall score"><div className="score-ring">{data.overall_score === null ? '—' : `${data.overall_score}%`}</div></Card>
        <Card title="Rank">
          {data.ranking_visible
            ? <><div className="score-ring">{ordinal(data.rank)} <span className="muted" style={{ fontSize: '1rem' }}>of {data.companies_count}</span></div>{data.percentile > 0 && <p className="muted small">Better than {data.percentile}% of participating companies.</p>}</>
            : <p className="muted">Ranking is not shown for rounds with fewer than 3 participating companies (this protects anonymity).</p>}
        </Card>
      </div>
      {data.peer_distribution?.length > 0 && <Card title="Peer distribution (anonymous)"><BarList ariaLabel="Peer comparison" rows={data.peer_distribution.map((p) => ({ label: p.label, score: p.score, self: p.is_self }))} /></Card>}
      <div className="grid2">
        <Card title="By recording"><BarList ariaLabel="Score per recording" rows={data.per_recording.map((r) => ({ label: r.title, score: r.score }))} /></Card>
        <Card title="By key-point category"><BarList ariaLabel="Score per category" rows={data.per_category.map((c) => ({ label: c.category[0].toUpperCase() + c.category.slice(1), score: c.score }))} /></Card>
      </div>
      {data.pairwise_win_rate !== undefined && <Card title="Head-to-head"><p>Win rate in direct comparisons: <strong>{data.pairwise_win_rate}%</strong></p></Card>}
      {summary && <Card title="Summary"><pre className="md">{summary}</pre></Card>}
      <p className="muted small">{data.methodology}</p>
    </div>
  )
}
