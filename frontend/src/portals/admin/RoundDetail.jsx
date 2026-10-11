import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { api, download, fieldErrors } from '../../shared/api'
import AudioPlayer from '../../shared/AudioPlayer'
import ReportView from '../../shared/ReportView'
import { useAction, useGet } from '../../shared/hooks'
import { Badge, Button, Card, Empty, Modal, Progress, Query, StatusBadge, Table, Tabs, TextInput, useToast } from '../../shared/ui'
import { countdown, fmtDate, toLocalInput } from '../../shared/util'
import { KeyPointsEditor } from './Rounds'

const TABS = [['overview', 'Overview & tracker'], ['key', 'Answer key'], ['dist', 'Distribution'], ['scores', 'Scores'], ['pairs', 'Pairwise'], ['reports', 'Reports']]

export default function RoundDetail() {
  const { id } = useParams()
  const [tab, setTab] = useState('overview')
  const q = useGet(`/admin/rounds/${id}/`)
  return (
    <div className="stack">
      <Query q={q}>{(r) => (
        <>
          <div className="page-head">
            <div><Link to="/admin/rounds" className="small">← Rounds</Link><h1 style={{ marginBottom: 0 }}>{r.name} <StatusBadge status={r.status} /></h1>
              <span className="muted small">{r.language} · deadline {fmtDate(r.deadline)} {r.status === 'open' && `· ${countdown(r.deadline)}`}</span></div>
            {r.status === 'draft' && <Link className="btn primary" to={`/admin/rounds/${r.id}/edit`}>Edit in wizard</Link>}
          </div>
          <Tabs tabs={TABS.map(([key, label]) => ({ key, label }))} value={tab} onChange={setTab} />
          {tab === 'overview' && <Overview round={r} />}
          {tab === 'key' && <AnswerKey round={r} />}
          {tab === 'dist' && <Distribution round={r} />}
          {tab === 'scores' && <Scores round={r} />}
          {tab === 'pairs' && <Pairwise round={r} />}
          {tab === 'reports' && <Reports round={r} />}
        </>
      )}</Query>
    </div>
  )
}

// ------------------------------------------------------------------ overview + tracker
function Overview({ round: r }) {
  const { toast, confirm } = useToast()
  const qc = useQueryClient()
  const tracker = useGet(`/admin/rounds/${r.id}/submission-status/`, { refetchInterval: 20000, enabled: r.status !== 'draft' })
  const [selected, setSelected] = useState([])
  const [extend, setExtend] = useState(null)
  const refresh = () => { qc.invalidateQueries({ queryKey: [`/admin/rounds/${r.id}/`] }); qc.invalidateQueries({ queryKey: [`/admin/rounds/${r.id}/submission-status/`] }); qc.invalidateQueries({ queryKey: ['/admin/dashboard/'] }) }
  const act = (path, success, body) => async () => { try { await api.post(`/admin/rounds/${r.id}/${path}/`, body); toast(success); refresh() } catch (e) { toast.error(e) } }

  const remind = async (ids) => { try { const d = (await api.post(`/admin/rounds/${r.id}/reminders/`, ids ? { assignment_ids: ids } : { all: true })).data; toast(`${d.sent} reminder(s) sent.`) } catch (e) { toast.error(e) } }
  const doExtend = async () => {
    try { await api.post(`/admin/rounds/${r.id}/extend/`, { deadline: new Date(extend.deadline).toISOString(), ...(extend.scope === 'company' ? { company_id: extend.company_id } : extend.scope === 'interpreter' ? { assignment_id: extend.assignment_id } : {}) }); toast('Deadline extended.'); setExtend(null); refresh() } catch (e) { toast.error(e) }
  }
  const delAudio = async () => {
    if (!(await confirm({ title: 'Delete all audio?', message: 'This permanently deletes every interpretation recording for this round (scores and aggregates remain).', danger: true, confirmLabel: 'Continue' }))) return
    if (!(await confirm({ title: 'Really delete?', message: 'This cannot be undone. Delete the audio now?', danger: true, confirmLabel: 'Delete audio now' }))) return
    try { const d = (await api.post(`/admin/rounds/${r.id}/delete-audio/`, { confirm: true })).data; toast(`${d.files_deleted} file(s) deleted.`); refresh() } catch (e) { toast.error(e) }
  }
  const expires = r.status === 'released' || r.status === 'archived' ? new Date(new Date(r.deadline).getTime() + r.retention_days * 864e5) : null

  return (
    <div className="stack">
      <Card title="Actions">
        <div className="row">
          {r.status === 'open' && <><Button variant="primary" onClick={async () => { if (await confirm({ message: 'Close the round now? Interpreters will no longer be able to upload.' })) act('close', 'Round closed.')() }}>Close round</Button>
            <Button onClick={() => remind()}>Remind all non-submitted</Button>
            <Button onClick={() => setExtend({ scope: 'round', deadline: toLocalInput(Date.now() + 3 * 864e5) })}>Extend deadline</Button></>}
          {r.status === 'closed' && <Button variant="primary" onClick={() => setExtend({ scope: 'reopen', deadline: toLocalInput(Date.now() + 3 * 864e5) })}>Re-open (extend deadline)</Button>}
          {r.status === 'draft' && <Button variant="primary" onClick={act('open', 'Round opened — invitations sent.')}>Open round</Button>}
          {r.status === 'released' && <Button onClick={act('archive', 'Round archived.')}>Archive</Button>}
          {['review', 'released', 'archived'].includes(r.status) && !r.audio_deleted_at && <Button variant="danger" onClick={delAudio}>Delete audio now</Button>}
          <Button onClick={() => download(`/admin/rounds/${r.id}/export.xlsx`, `eqal-round-${r.id}.xlsx`).catch(toast.error)}>Export Excel</Button>
          {r.status === 'draft' && <Button variant="danger" onClick={async () => { if (await confirm({ message: 'Delete this draft?', danger: true })) { await api.delete(`/admin/rounds/${r.id}/`); window.location.assign('/admin/rounds') } }}>Delete draft</Button>}
        </div>
        <div className="muted small" style={{ marginTop: 10 }}>Retention: audio deleted {r.retention_days} days after the deadline{expires && !r.audio_deleted_at ? ` (≈ ${fmtDate(expires)}, ${countdown(expires).replace('left', 'remaining')})` : ''}{r.audio_deleted_at ? ` — deleted ${fmtDate(r.audio_deleted_at)}` : ''}.</div>
        <div style={{ marginTop: 10 }}><div className="row between small"><span>Submitted</span><strong>{r.submitted}/{r.assignments_total}</strong></div><Progress value={r.submitted} max={r.assignments_total} /></div>
      </Card>

      {r.status === 'draft' ? <Empty>Draft — open the round to see the submission tracker.</Empty> : (
        <Query q={tracker}>{(t) => (
          <Card title="Submission tracker" actions={selected.length > 0 && <Button size="sm" onClick={() => remind(selected)}>Remind {selected.length} selected</Button>}>
            {t.companies.map((c) => (
              <div key={c.company_id} style={{ marginBottom: 16 }}>
                <div className="row between"><h3>{c.company} <span className="muted small">{c.submitted}/{c.total} submitted</span> {c.deadline_override && <Badge tone="info">extended {fmtDate(c.deadline_override)}</Badge>}</h3>
                  {r.status === 'open' && <Button size="sm" onClick={() => setExtend({ scope: 'company', company_id: c.company_id, deadline: toLocalInput(Date.now() + 3 * 864e5) })}>Extend for company</Button>}</div>
                <Table empty="No interpreters." rows={c.interpreters.map((i) => ({ ...i, id: i.assignment_id }))} columns={[
                  { label: '', render: (i) => i.status !== 'submitted' && <input type="checkbox" aria-label={`Select ${i.interpreter}`} checked={selected.includes(i.assignment_id)} onChange={(e) => setSelected(e.target.checked ? [...selected, i.assignment_id] : selected.filter((x) => x !== i.assignment_id))} /> },
                  { label: 'Interpreter', render: (i) => <>{i.interpreter}<div className="muted small">{i.email}</div></> },
                  { label: 'Status', render: (i) => <StatusBadge status={i.status} /> },
                  ...t.recordings.map((rec) => ({ label: rec.title, render: (i) => (i.per_recording[rec.id] ? '✅' : '—') })),
                  { label: 'Deadline', render: (i) => fmtDate(i.deadline) },
                  { label: '', render: (i) => r.status === 'open' && i.status !== 'submitted' && <div className="row"><Button size="sm" onClick={() => remind([i.assignment_id])}>Remind</Button><Button size="sm" onClick={() => setExtend({ scope: 'interpreter', assignment_id: i.assignment_id, deadline: toLocalInput(Date.now() + 3 * 864e5) })}>Extend</Button></div> },
                ]} />
              </div>
            ))}
          </Card>
        )}</Query>
      )}
      {extend && (
        <Modal title={extend.scope === 'reopen' ? 'Re-open round' : 'Extend deadline'} onClose={() => setExtend(null)}
          actions={<><Button onClick={() => setExtend(null)}>Cancel</Button><Button variant="primary" onClick={async () => { if (extend.scope === 'reopen') { try { await api.post(`/admin/rounds/${r.id}/open/`, { deadline: new Date(extend.deadline).toISOString() }); toast('Round re-opened.'); setExtend(null); refresh() } catch (e) { toast.error(e) } } else doExtend() }}>Confirm</Button></>}>
          <p className="muted">Scope: <strong>{extend.scope}</strong>. Affected interpreters who have not submitted get an email.</p>
          <TextInput label="New deadline" type="datetime-local" value={extend.deadline} onChange={(e) => setExtend({ ...extend, deadline: e.target.value })} />
        </Modal>
      )}
    </div>
  )
}

function AnswerKey({ round: r }) {
  const qc = useQueryClient()
  const [sel, setSel] = useState(r.recordings[0]?.id)
  const reload = () => qc.invalidateQueries({ queryKey: [`/admin/rounds/${r.id}/`] })
  const locked = ['rating', 'review', 'released', 'archived'].includes(r.status)
  if (!r.recordings.length) return <Empty>No recordings.</Empty>
  return (
    <Card title="Answer key" actions={<Badge tone="warn">admin only</Badge>}>
      {locked && <div className="alert warn">The answer key is locked once rating has started.</div>}
      <div className="tabs">{r.recordings.map((x) => <button key={x.id} className={sel === x.id ? 'active' : ''} onClick={() => setSel(x.id)}>{x.title}</button>)}</div>
      {r.recordings.filter((x) => x.id === sel).map((x) => <KeyPointsEditor key={x.id} recording={x} locked={locked} onChanged={reload} />)}
    </Card>
  )
}

// ------------------------------------------------------------------ distribution
function Distribution({ round: r }) {
  const qc = useQueryClient()
  const { confirm, toast } = useToast()
  const [k, setK] = useState(r.min_raters_per_item)
  const [pw, setPw] = useState(r.pairwise_per_item)
  const [prev, setPrev] = useState(null)
  const preview = useAction(async () => (await api.post(`/admin/rounds/${r.id}/distribute/`, { dry_run: true, raters_per_item: k, pairwise_per_item: pw })).data, { onSuccess: setPrev })
  const go = useAction(async () => (await api.post(`/admin/rounds/${r.id}/distribute/`, { raters_per_item: k, pairwise_per_item: pw })).data,
    { success: (d) => `Distributed ${d.items} items → ${d.tasks} tasks, ${d.pairs} pairs.`, onSuccess: () => qc.invalidateQueries() })
  if (r.status !== 'closed') return <Card title="Distribution"><p>{r.status === 'rating' || r.status === 'review' || r.status === 'released' ? 'This round has already been distributed to raters. Manage individual tasks from the Scores tab.' : 'Distribution is possible once the round is closed.'}</p></Card>
  return (
    <Card title="Distribute to raters">
      <p className="muted">Creates anonymous items (random codes, renamed audio copies), assigns raters by language and load, and mixes companies so no rater gets a cluster of one company.</p>
      <div className="grid2"><TextInput label="Raters per item" type="number" min="1" value={k} onChange={(e) => setK(e.target.value)} /><TextInput label="Pairwise comparisons per item" type="number" min="0" value={pw} onChange={(e) => setPw(e.target.value)} /></div>
      <div className="row"><Button onClick={() => preview.mutate()} disabled={preview.isPending}>Preview load</Button>
        <Button variant="primary" disabled={go.isPending} onClick={async () => { if (await confirm({ message: 'Distribute now? The round moves to Rating and submissions are locked for good.' })) go.mutate() }}>Distribute</Button></div>
      {prev && <div style={{ marginTop: 14 }}><p><strong>{prev.items}</strong> items · <strong>{prev.pairs}</strong> pairwise comparisons</p>
        <Table rows={prev.raters.map((x) => ({ ...x, id: x.rater_id }))} columns={[{ label: 'Rater', key: 'email' }, { label: 'Scoring tasks', key: 'tasks' }, { label: 'Pairs', key: 'pairs' }]} /></div>}
    </Card>
  )
}

// ------------------------------------------------------------------ scores
function Scores({ round: r }) {
  const q = useGet(`/admin/rounds/${r.id}/scores/`, { enabled: ['rating', 'review', 'released', 'archived'].includes(r.status), refetchInterval: 30000 })
  const [open, setOpen] = useState(null)
  const qc = useQueryClient()
  const { toast, confirm } = useToast()
  if (!['rating', 'review', 'released', 'archived'].includes(r.status)) return <Card title="Scores"><p className="muted">Scores appear once the round has been distributed.</p></Card>
  const toReview = async () => {
    try { await api.post(`/admin/rounds/${r.id}/review/`, {}); qc.invalidateQueries(); toast('Round moved to Review.') } catch (e) {
      if (await confirm({ message: `${e.response?.data?.message} Force the move to Review?`, danger: true, confirmLabel: 'Force' })) { await api.post(`/admin/rounds/${r.id}/review/`, { force: true }); qc.invalidateQueries() }
    }
  }
  return (
    <Query q={q}>{(d) => (
      <div className="stack">
        <Card title="Rating progress" actions={r.status === 'rating' && <Button onClick={toReview}>Move to Review</Button>}>
          <div className="row between small"><span>Tasks complete</span><strong>{d.progress.done}/{d.progress.total}</strong></div><Progress value={d.progress.done} max={d.progress.total} />
          <p className="muted small" style={{ marginTop: 10 }}>{d.agreement.flagged} item(s) flagged for disagreement (spread &gt; {d.agreement.threshold} points). Mean spread: {d.agreement.mean_spread ?? '—'}.</p>
          <div className="row">{d.raters.map((x) => <Badge key={x.rater_id} tone={x.done === x.assigned ? 'ok' : ''}>{x.email}: {x.done}/{x.assigned}</Badge>)}</div>
        </Card>
        <Card title="Items (admin view — identities visible)">
          <Table empty="No items." rows={d.items} rowClass={(i) => (i.flagged ? 'flag' : '')} onRow={(i) => setOpen(i.id)} columns={[
            { label: 'Code', render: (i) => <strong>{i.code}</strong> }, { label: 'Company', key: 'company' }, { label: 'Interpreter', key: 'interpreter' }, { label: 'Recording', key: 'recording' },
            { label: 'Score', render: (i) => <>{i.score ?? '—'}{i.override_score !== null && <Badge tone="info"> override</Badge>}</> },
            { label: 'Spread', render: (i) => <>{i.spread ?? '—'} {i.flagged && <Badge tone="warn">review</Badge>}</> },
            { label: 'Raters', render: (i) => i.raters.map((x) => <span key={x.task_id} title={x.rater} className={`badge ${x.excluded ? 'bad' : x.status === 'done' ? 'ok' : ''}`} style={{ marginRight: 4 }}>{x.score ?? x.status}</span>) },
          ]} />
        </Card>
        {open && <ItemModal id={open} onClose={() => setOpen(null)} round={r} />}
      </div>
    )}</Query>
  )
}

function ItemModal({ id, onClose, round }) {
  const q = useGet(`/admin/items/${id}/`)
  const raters = useGet('/admin/raters/')
  const qc = useQueryClient()
  const { toast } = useToast()
  const [ov, setOv] = useState({ score: '', reason: '' })
  const [excl, setExcl] = useState({})
  const [errs, setErrs] = useState({})
  const reload = () => { qc.invalidateQueries({ queryKey: [`/admin/items/${id}/`] }); qc.invalidateQueries({ queryKey: [`/admin/rounds/${round.id}/scores/`] }) }
  const call = async (fn, msg) => { try { await fn(); toast(msg); reload() } catch (e) { setErrs(fieldErrors(e)); toast.error(e) } }
  const frozen = ['released', 'archived'].includes(round.status)
  return (
    <Modal wide title="Item detail" onClose={onClose} actions={<Button onClick={onClose}>Close</Button>}>
      <Query q={q}>{(d) => (
        <div className="stack">
          <div className="row between"><div><strong>{d.code}</strong> · {d.company} · {d.interpreter} · {d.recording}</div><div className="stat">{d.score ?? '—'}</div></div>
          <div className="split"><AudioPlayer url={d.source_audio_url} label="Original" /><AudioPlayer url={d.interpretation_audio_url} label="Interpretation" /></div>
          {!frozen && <Card title="Override score">
            <div className="row" style={{ alignItems: 'flex-end' }}><div style={{ width: 120 }}><TextInput label="Score 0-100" type="number" min="0" max="100" error={errs.score} value={ov.score} onChange={(e) => setOv({ ...ov, score: e.target.value })} /></div>
              <div style={{ flex: 1 }}><TextInput label="Reason (required, audited)" error={errs.reason} value={ov.reason} onChange={(e) => setOv({ ...ov, reason: e.target.value })} /></div>
              <div style={{ marginBottom: 12 }} className="row"><Button variant="primary" onClick={() => call(() => api.post(`/admin/items/${id}/override/`, ov), 'Override saved.')}>Apply</Button>
                {d.override_score !== null && <Button onClick={() => call(() => api.post(`/admin/items/${id}/override/`, { score: null }), 'Override cleared.')}>Clear</Button>}</div></div>
            {d.override_score !== null && <p className="muted small">Current override: {d.override_score} — “{d.override_reason}”. Auto score: {d.auto_score ?? '—'}</p>}
          </Card>}
          {d.raters.map((rt) => (
            <Card key={rt.task_id} title={rt.rater} actions={<><StatusBadge status={rt.status} />{rt.excluded && <Badge tone="bad">excluded</Badge>}<strong>{rt.score ?? '—'}</strong></>}>
              <Table rows={rt.checklist.map((c) => ({ ...c, id: c.key_point }))} columns={[{ label: 'Key point', render: (c) => <>{c.text} <span className="muted small">({c.category})</span></> }, { label: 'Value', render: (c) => c.value || '—' }, { label: 'Comment', key: 'comment' }]} />
              {rt.overall_comment && <p className="small"><strong>Overall:</strong> {rt.overall_comment}</p>}
              {!frozen && <div className="row" style={{ marginTop: 10 }}>
                {rt.excluded ? <Button size="sm" onClick={() => call(() => api.post(`/admin/tasks/${rt.task_id}/exclude/`, { excluded: false }), 'Rater included.')}>Include again</Button>
                  : <><input style={{ width: 220 }} placeholder="Exclusion reason" aria-label="Exclusion reason" value={excl[rt.task_id] || ''} onChange={(e) => setExcl({ ...excl, [rt.task_id]: e.target.value })} />
                    <Button size="sm" onClick={() => call(() => api.post(`/admin/tasks/${rt.task_id}/exclude/`, { excluded: true, reason: excl[rt.task_id] }), 'Rater excluded.')}>Exclude</Button></>}
                {rt.status === 'done' && <Button size="sm" onClick={() => call(() => api.post(`/admin/tasks/${rt.task_id}/unlock/`), 'Task unlocked for editing.')}>Unlock</Button>}
                {rt.status !== 'done' && <select aria-label="Reassign to" defaultValue="" style={{ width: 200 }} onChange={(e) => e.target.value && call(() => api.post(`/admin/tasks/${rt.task_id}/reassign/`, { rater_id: e.target.value }), 'Task reassigned.')}>
                  <option value="">Reassign to…</option>{(raters.data || []).filter((x) => x.active).map((x) => <option key={x.id} value={x.id}>{x.email}</option>)}</select>}
              </div>}
            </Card>
          ))}
        </div>
      )}</Query>
    </Modal>
  )
}

function Pairwise({ round: r }) {
  const q = useGet(`/admin/rounds/${r.id}/pairwise/`, { enabled: ['rating', 'review', 'released', 'archived'].includes(r.status) })
  if (!['rating', 'review', 'released', 'archived'].includes(r.status)) return <Card title="Pairwise"><p className="muted">Available after distribution.</p></Card>
  return (
    <Query q={q}>{(d) => (
      <div className="stack">
        <Card title="Win rate by company (admin analysis)"><Table empty="No comparisons completed yet." rows={d.company_win_rate.map((x, i) => ({ ...x, id: i }))} columns={[{ label: 'Company', key: 'company' }, { label: 'Win rate', render: (x) => `${x.win_rate}%` }]} /></Card>
        <Card title="Comparisons"><Table empty="No pairs." rows={d.pairs} columns={[
          { label: 'Recording', key: 'recording' }, { label: 'Rater', key: 'rater' },
          { label: 'A', render: (p) => `${p.a} (${p.a_company})` }, { label: 'B', render: (p) => `${p.b} (${p.b_company})` },
          { label: 'Winner', render: (p) => p.winner ? p.winner.toUpperCase() : <span className="muted">pending</span> }, { label: 'Comment', key: 'comment' }]} /></Card>
      </div>
    )}</Query>
  )
}

// ------------------------------------------------------------------ reports
function Reports({ round: r }) {
  const q = useGet(`/admin/rounds/${r.id}/reports/`)
  const qc = useQueryClient()
  const { confirm, toast } = useToast()
  const [open, setOpen] = useState(null)
  const reload = () => { qc.invalidateQueries({ queryKey: [`/admin/rounds/${r.id}/reports/`] }); qc.invalidateQueries({ queryKey: [`/admin/rounds/${r.id}/`] }) }
  const gen = useAction(async () => (await api.post(`/admin/rounds/${r.id}/reports/generate/`)).data, { success: (d) => `${d.generated} draft report(s) generated.`, onSuccess: reload })
  const relAll = useAction(async () => (await api.post(`/admin/rounds/${r.id}/reports/release-all/`)).data, { success: (d) => `${d.released} report(s) released.`, onSuccess: () => qc.invalidateQueries() })
  const approve = useAction(async (id) => api.post(`/admin/reports/${id}/approve/`), { success: 'Approved.', onSuccess: reload })
  const release = useAction(async (id) => api.post(`/admin/reports/${id}/release/`), { success: 'Released — company notified.', onSuccess: () => qc.invalidateQueries() })
  return (
    <div className="stack">
      <Card title="Company reports" actions={<>
        {r.status === 'review' && <Button variant="primary" onClick={() => gen.mutate()} disabled={gen.isPending}>Generate / regenerate drafts</Button>}
        <Button disabled={!q.data?.some((x) => x.status === 'approved')} onClick={async () => { if (await confirm({ message: 'Release all approved reports? Companies are notified and the reports become immutable.' })) relAll.mutate() }}>Release all approved</Button></>}>
        {r.status !== 'review' && r.status !== 'released' && <div className="alert">Reports can be generated once the round reaches the Review stage.</div>}
        <Query q={q}>{(rows) => <Table empty="No reports generated yet." rows={rows} columns={[
          { label: 'Company', key: 'company' }, { label: 'Score', render: (x) => x.overall_score ?? '—' }, { label: 'Rank', render: (x) => x.rank ?? '—' },
          { label: 'Status', render: (x) => <StatusBadge status={x.status} /> }, { label: 'Released', render: (x) => fmtDate(x.released_at) },
          { label: '', render: (x) => <div className="row"><Button size="sm" onClick={() => setOpen(x.id)}>{x.status === 'released' ? 'View' : 'Preview / edit'}</Button>
            {x.status === 'draft' && <Button size="sm" onClick={() => approve.mutate(x.id)}>Approve</Button>}
            {x.status === 'approved' && <Button size="sm" variant="primary" onClick={async () => { if (await confirm({ message: `Release the report to ${x.company}?` })) release.mutate(x.id) }}>Release</Button>}</div> },
        ]} />}</Query>
      </Card>
      {open && <ReportModal id={open} onClose={() => setOpen(null)} onSaved={reload} />}
    </div>
  )
}

function ReportModal({ id, onClose, onSaved }) {
  const q = useGet(`/admin/reports/${id}/`)
  const { toast } = useToast()
  const [text, setText] = useState(null)
  return (
    <Modal wide title="Report preview" onClose={onClose} actions={<Button onClick={onClose}>Close</Button>}>
      <Query q={q}>{(d) => {
        const summary = text ?? d.summary
        return (
          <div className="stack">
            <div className="alert">This is exactly what <strong>{d.company}</strong> will see.</div>
            <ReportView data={d.data} summary={summary} />
            {d.status !== 'released' && <Card title="Summary text">
              <textarea aria-label="Summary" value={summary} onChange={(e) => setText(e.target.value)} style={{ minHeight: 140 }} />
              <div className="row" style={{ marginTop: 8 }}><Button variant="primary" onClick={async () => { try { await api.patch(`/admin/reports/${id}/`, { summary }); toast('Summary saved.'); onSaved(); q.refetch() } catch (e) { toast.error(e) } }}>Save summary</Button>
                {d.status === 'approved' && <span className="muted small">Saving moves an approved report back to draft.</span>}</div>
              {d.comments.length > 0 && <details style={{ marginTop: 12 }}><summary>Rater comments for this company ({d.comments.length}) — anonymous, for drafting</summary>
                <ul>{d.comments.map((c, i) => <li key={i} className="small"><strong>{c.recording}</strong> · {c.key_point} {c.value && `(${c.value})`}: {c.comment}</li>)}</ul></details>}
            </Card>}
          </div>
        )
      }}</Query>
    </Modal>
  )
}
