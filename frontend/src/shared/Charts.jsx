/** Horizontal bars. rows: [{label, score, self?}] with score 0-100. */
export function BarList({ rows, ariaLabel }) {
  return (
    <div className="bars" role="list" aria-label={ariaLabel}>
      {rows.map((r, i) => (
        <div className="bar-row" role="listitem" key={i}>
          <span title={r.label}>{r.label}</span>
          <div className="bar-track"><div className={`bar-fill ${r.self ? 'self' : ''}`} style={{ width: `${r.score ?? 0}%` }} /></div>
          <strong>{r.score === null || r.score === undefined ? '—' : `${Math.round(r.score)}%`}</strong>
        </div>
      ))}
    </div>
  )
}

/** Simple SVG line chart. points: [{label, value}] */
export function LineChart({ points, max = 100, height = 180, unit = '%', invert = false }) {
  const pts = points.filter((p) => p.value !== null && p.value !== undefined)
  if (!pts.length) return <div className="empty">No data yet.</div>
  const w = 560; const pad = 34
  const x = (i) => pad + (pts.length === 1 ? (w - 2 * pad) / 2 : (i * (w - 2 * pad)) / (pts.length - 1))
  const y = (v) => { const f = invert ? (v - 1) / (max - 1) : 1 - v / max; return 12 + f * (height - 40) }
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" role="img" aria-label="Trend over rounds" style={{ maxWidth: 700 }}>
      {[0, 0.5, 1].map((f) => <line key={f} x1={pad} x2={w - pad} y1={12 + f * (height - 40)} y2={12 + f * (height - 40)} stroke="var(--border)" />)}
      <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2.5" />
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(p.value)} r="4.5" fill="var(--primary)" />
          <text x={x(i)} y={y(p.value) - 9} textAnchor="middle" fontSize="11" fill="var(--text)">{p.value}{unit}</text>
          <text x={x(i)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--muted)">{String(p.label).slice(0, 14)}</text>
        </g>
      ))}
    </svg>
  )
}
