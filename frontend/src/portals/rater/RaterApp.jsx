import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { api, errCode, errMsg } from '../../shared/api'
import AudioPlayer from '../../shared/AudioPlayer'
import PortalLayout from '../../shared/Layout'
import ScoringPanel from '../../shared/ScoringPanel'
import { ErrorPage } from '../../shared/pages'
import { useGet } from '../../shared/hooks'
import { Badge, Button, Card, Empty, Progress, Query, StatusBadge, Table, useToast } from '../../shared/ui'
import { fmtDate } from '../../shared/util'

const LINKS = [
  { to: '/rater', label: 'Dashboard', end: true }, { to: '/rater/practice', label: 'Practice' },
  { to: '/rater/tasks', label: 'Scoring tasks' }, { to: '/rater/pairs', label: 'Compare two' },
]

function Locked() {
  return <div className="alert warn" role="alert">Real tasks are locked until you have completed the practice items. <Link to="/rater/practice">Go to practice →</Link></div>
}

function Dashboard() {
  const q = useGet('/rater/dashboard/', { refetchInterval: 30000 })
  return (
    <div className="stack"><h1>Dashboard</h1>
      <Query q={q}>{(d) => (<>
        {d.locked && <Locked />}
        <div className="grid">
          <Card title="Practice"><div className="stat">{d.practice_done}/{d.practice_total}</div><p className="muted small">{d.is_calibrated ? 'Calibrated ✓' : 'Complete all practice items to unlock real tasks.'}</p><Link className="btn" to="/rater/practice">Open practice</Link></Card>
          <Card title="Scoring tasks"><div className="row"><div><div className="stat">{d.todo}</div><span className="muted small">to do</span></div><div><div className="stat">{d.in_progress}</div><span className="muted small">in progress</span></div><div><div className="stat">{d.done}</div><span className="muted small">done</span></div></div>
            {d.next_due && <p className="muted small">Next due {fmtDate(d.next_due)}</p>}<Link className="btn primary" to="/rater/tasks">Open tasks</Link></Card>
          <Card title="Compare two"><div className="stat">{d.pairs_done}/{d.pairs_total}</div><Progress value={d.pairs_done} max={d.pairs_total} /><p /><Link className="btn" to="/rater/pairs">Start comparing</Link></Card>
        </div></>)}</Query>
    </div>
  )
}

// ------------------------------------------------------------------ practice
function PracticeList() {
  const q = useGet('/rater/practice/')
  return (
    <div className="stack"><h1>Practice</h1><p className="muted">Score these sample items, then compare your answers with the reference scores.</p>
      <Query q={q}>{(rows) => <Table empty="No practice items — you can go straight to real tasks." rows={rows} columns={[{ label: 'Item', render: (p) => <Link to={`/rater/practice/${p.id}`}><strong>{p.title}</strong></Link> }, { label: 'Language', key: 'language' }, { label: 'Your last agreement', render: (p) => (p.attempted ? <Badge tone={p.agreement >= 80 ? 'ok' : 'warn'}>{p.agreement}%</Badge> : <Badge>not attempted</Badge>) }]} />}</Query></div>
  )
}

function Practice() {
  const { id } = useParams()
  const q = useGet(`/rater/practice/${id}/`)
  return <Query q={q}>{(d) => <PracticeInner key={`${id}-${d.last_answers ? 1 : 0}`} d={d} id={id} reload={q.refetch} />}</Query>
}

function PracticeInner({ d, id }) {
  const [scores, setScores] = useState({})
  const [cur, setCur] = useState(0)
  const [result, setResult] = useState(null)
  const { toast } = useToast()
  const qc = useQueryClient()
  const set = useCallback((kp, patch) => setScores((s) => ({ ...s, [kp]: { ...s[kp], ...patch } })), [])
  const done = d.key_points.every((k) => scores[k.id]?.value)
  const submit = async () => {
    try { const r = (await api.post(`/rater/practice/${id}/score/`, { answers: Object.fromEntries(d.key_points.map((k) => [k.id, scores[k.id].value])) })).data; setResult(r); qc.invalidateQueries() } catch (e) { toast.error(e) }
  }
  const reference = result && Object.fromEntries(result.feedback.map((f) => [f.key_point, { reference: f.reference, match: f.match, explanation: f.explanation }]))
  return (
    <div className="stack">
      <Link to="/rater/practice" className="small">← Practice</Link><h1>{d.title}</h1>
      <div className="split">{d.source_audio_url && <AudioPlayer url={d.source_audio_url} label="Original" />}{d.interpretation_audio_url && <AudioPlayer url={d.interpretation_audio_url} label="Interpretation" />}</div>
      {result && <div className={`alert ${result.agreement >= 80 ? 'ok' : 'warn'}`}><strong>Agreement with reference: {result.agreement}%</strong>{result.is_calibrated && ' — you are calibrated, real tasks are unlocked 🎉'}</div>}
      <ScoringPanel keyPoints={d.key_points} scores={scores} onChange={set} disabled={!!result} current={cur} setCurrent={setCur} showComments={false} reference={reference} />
      <div className="row">{!result ? <Button variant="primary" disabled={!done} onClick={submit}>Submit & see feedback</Button> : <><Button onClick={() => { setResult(null); setScores({}) }}>Try again</Button><Link className="btn primary" to="/rater/practice">Back to list</Link></>}</div>
    </div>
  )
}

// ------------------------------------------------------------------ real tasks
function Tasks() {
  const [status, setStatus] = useState('')
  const q = useGet(`/rater/tasks/${status ? `?status=${status}` : ''}`)
  return (
    <div className="stack"><div className="page-head"><h1>Scoring tasks</h1><select aria-label="Filter" style={{ width: 160 }} value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="todo">To do</option><option value="in_progress">In progress</option><option value="done">Done</option></select></div>
      <Query q={q}>{(d) => d.locked ? <Locked /> : <Table empty="No tasks for you right now." rows={d.tasks} columns={[{ label: 'Code', render: (t) => <Link to={`/rater/tasks/${t.id}`}><strong>{t.code}</strong></Link> }, { label: 'Recording', key: 'recording_title' }, { label: 'Status', render: (t) => <StatusBadge status={t.status} /> }, { label: 'Due', render: (t) => fmtDate(t.due_at) }, { label: '', render: (t) => <Link className="btn sm" to={`/rater/tasks/${t.id}`}>{t.status === 'done' ? 'View' : 'Score'}</Link> }]} />}</Query></div>
  )
}

function Task() {
  const { id } = useParams()
  const q = useGet(`/rater/tasks/${id}/`, { refetchOnWindowFocus: false, staleTime: Infinity, retry: false })
  if (q.isError && errCode(q.error) === 'calibration_required') return <Locked />
  return <Query q={q}>{(d) => <Scoring d={d} id={id} refetch={q.refetch} />}</Query>
}

function Scoring({ d, id, refetch }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [scores, setScores] = useState(d.scores)
  const [overall, setOverall] = useState(d.overall_comment)
  const [cur, setCur] = useState(() => Math.max(0, d.key_points.findIndex((k) => !d.scores[k.id])))
  const [save, setSave] = useState('saved')           // saved | saving | dirty | error
  const dirty = useRef({}); const dirtyOverall = useRef(false); const timer = useRef()
  const players = useRef({}); const lastPlayer = useRef('orig')
  const locked = d.locked || d.status === 'done'

  const flush = useCallback(async () => {
    clearTimeout(timer.current)
    const keys = Object.keys(dirty.current)
    if (!keys.length && !dirtyOverall.current) return true
    const payload = { scores: keys.map((k) => ({ key_point: Number(k), ...dirty.current[k] })) }
    const sentOverall = dirtyOverall.current
    if (sentOverall) payload.overall_comment = overall
    dirty.current = {}; dirtyOverall.current = false
    setSave('saving')
    try { await api.patch(`/rater/tasks/${id}/`, payload); setSave(Object.keys(dirty.current).length ? 'dirty' : 'saved'); return true }
    catch (e) { keys.forEach((k) => { dirty.current[k] = { ...payload.scores.find((s) => s.key_point === Number(k)), ...dirty.current[k] } }); dirtyOverall.current ||= sentOverall; setSave('error'); toast.error(e); return false }
  }, [id, overall, toast])
  const queue = useCallback(() => { setSave('dirty'); clearTimeout(timer.current); timer.current = setTimeout(flush, 600) }, [flush])
  useEffect(() => () => clearTimeout(timer.current), [])

  const change = useCallback((kp, patch) => {
    if (locked) return
    setScores((s) => { const n = { ...s[kp], ...patch }; dirty.current[kp] = { value: n.value, comment: n.comment || '' }; return { ...s, [kp]: n } })
    if (patch.value || patch.comment !== undefined) { if (!(patch.comment !== undefined && !patch.value && !scores[kp]?.value)) queue() }
  }, [locked, queue, scores])

  // Space = play / pause the player you used last
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space' || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(e.target.tagName)) return
      e.preventDefault(); players.current[lastPlayer.current]?.toggle()
    }
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey)
  }, [])

  const scored = d.key_points.filter((k) => scores[k.id]?.value).length
  const refresh = (field) => async () => (await refetch()).data[field]
  const complete = async () => {
    if (!(await flush())) return
    try { await api.post(`/rater/tasks/${id}/complete/`); toast('Marked complete.'); qc.invalidateQueries(); nav('/rater/tasks') } catch (e) { toast.error(e) }
  }
  const exit = async () => { if (await flush()) { qc.invalidateQueries(); nav('/rater/tasks') } }

  return (
    <div className="stack">
      <div className="page-head"><div><Link to="/rater/tasks" className="small">← Tasks</Link><h1 style={{ marginBottom: 0 }}>{d.code} <span className="muted" style={{ fontSize: '1rem', fontWeight: 400 }}>· {d.recording_title}</span></h1></div>
        <div className="row"><span className="small muted" aria-live="polite">{save === 'saving' ? 'Saving…' : save === 'error' ? '⚠ Not saved' : save === 'dirty' ? 'Unsaved changes…' : '✓ All changes saved'}</span><StatusBadge status={locked ? 'done' : d.status} /></div></div>
      {locked && <div className="alert">This task is complete and locked. Ask an admin if it needs to be unlocked.</div>}
      <div className="split">
        <AudioPlayer ref={(r) => { players.current.orig = r }} url={d.source_audio_url} label="Original" refresh={refresh('source_audio_url')} active={lastPlayer.current === 'orig'} onPlay={() => { lastPlayer.current = 'orig' }} />
        <AudioPlayer ref={(r) => { players.current.interp = r }} url={d.interpretation_audio_url} label="Interpretation" refresh={refresh('interpretation_audio_url')} active={lastPlayer.current === 'interp'} onPlay={() => { lastPlayer.current = 'interp' }} />
      </div>
      <p className="muted small"><span className="kbd">1</span> Fully · <span className="kbd">2</span> Partly · <span className="kbd">3</span> Lost · <span className="kbd">↑</span><span className="kbd">↓</span> move · <span className="kbd">Space</span> play/pause</p>
      <div className="row between small"><span>{scored} of {d.key_points.length} key points scored</span></div><Progress value={scored} max={d.key_points.length} />
      <ScoringPanel keyPoints={d.key_points} scores={scores} onChange={change} disabled={locked} current={cur} setCurrent={setCur} />
      <div className="field"><label htmlFor="oc">Overall comment (optional)</label>
        <textarea id="oc" value={overall} disabled={locked} onChange={(e) => { setOverall(e.target.value); dirtyOverall.current = true; queue() }} /></div>
      {!locked && <div className="row"><Button onClick={exit}>Save & exit</Button><Button variant="primary" disabled={scored < d.key_points.length} onClick={complete}>Mark complete</Button>{scored < d.key_points.length && <span className="muted small">Score every key point to enable.</span>}</div>}
    </div>
  )
}

// ------------------------------------------------------------------ compare two
function Pairs() {
  const q = useGet('/rater/pairs/')
  return (
    <div className="stack"><h1>Compare two</h1><p className="muted">For each pair, decide which interpretation conveyed the original better.</p>
      <Query q={q}>{(d) => {
        if (d.locked) return <Locked />
        const todo = d.pairs.filter((p) => !p.done); const done = d.pairs.length - todo.length
        return (<><div className="row between small"><span>Progress</span><strong>{done}/{d.pairs.length}</strong></div><Progress value={done} max={d.pairs.length} />
          {todo.length > 0 && <div><Link className="btn primary" to={`/rater/pairs/${todo[0].id}`}>{done ? 'Continue' : 'Start'} comparing</Link></div>}
          <Table empty="No comparisons assigned to you." rows={d.pairs} columns={[{ label: '#', render: (p) => <Link to={`/rater/pairs/${p.id}`}>Pair {p.id}</Link> }, { label: 'Recording', key: 'recording_title' }, { label: 'Status', render: (p) => <Badge tone={p.done ? 'ok' : ''}>{p.done ? 'done' : 'to do'}</Badge> }]} /></>)
      }}</Query></div>
  )
}

function Compare() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { toast } = useToast()
  const q = useGet(`/rater/pairs/${id}/`, { refetchOnWindowFocus: false, staleTime: Infinity })
  const list = useGet('/rater/pairs/')
  const [winner, setWinner] = useState(null); const [comment, setComment] = useState('')
  useEffect(() => { setWinner(q.data?.winner || null); setComment(q.data?.comment || '') }, [q.data])
  const players = useRef({})
  useEffect(() => {
    const onKey = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(e.target.tagName)) return
      if (e.key === '1') setWinner('a'); else if (e.key === '2') setWinner('b'); else if (e.key === '3') setWinner('tie')
    }
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey)
  }, [])
  const submit = async () => {
    try {
      await api.post(`/rater/pairs/${id}/`, { winner, comment }); toast('Saved.'); qc.invalidateQueries({ queryKey: ['/rater/pairs/'] })
      const next = (await list.refetch()).data?.pairs.find((p) => !p.done && String(p.id) !== id)
      nav(next ? `/rater/pairs/${next.id}` : '/rater/pairs')
    } catch (e) { toast.error(errMsg(e)) }
  }
  const total = list.data?.pairs.length || 0; const done = list.data?.pairs.filter((p) => p.done).length || 0
  return (
    <div className="stack"><Link to="/rater/pairs" className="small">← Pairs</Link>
      <Query q={q}>{(d) => (<>
        <div className="page-head"><h1 style={{ marginBottom: 0 }}>{d.recording_title}</h1><span className="muted">{done}/{total} compared</span></div>
        <AudioPlayer url={d.source_audio_url} label="Original" refresh={async () => (await q.refetch()).data.source_audio_url} />
        <div className="split"><AudioPlayer url={d.a_audio_url} label="Interpretation A" refresh={async () => (await q.refetch()).data.a_audio_url} /><AudioPlayer url={d.b_audio_url} label="Interpretation B" refresh={async () => (await q.refetch()).data.b_audio_url} /></div>
        <div className="seg" role="group" aria-label="Which is better?" style={{ width: 'fit-content' }}>
          {[['a', 'A better (1)'], ['tie', 'About equal (3)'], ['b', 'B better (2)']].map(([v, l]) => <button key={v} type="button" aria-pressed={winner === v} className={winner === v ? 'full' : ''} onClick={() => setWinner(v)}>{l}</button>)}
        </div>
        <div className="field"><label htmlFor="pc">Comment (optional)</label><textarea id="pc" value={comment} onChange={(e) => setComment(e.target.value)} /></div>
        <div><Button variant="primary" disabled={!winner} onClick={submit}>Save & next</Button></div>
      </>)}</Query></div>
  )
}

export default function RaterApp() {
  return (
    <PortalLayout title="Rater" links={LINKS}>
      <Routes>
        <Route index element={<Dashboard />} /><Route path="practice" element={<PracticeList />} /><Route path="practice/:id" element={<Practice />} />
        <Route path="tasks" element={<Tasks />} /><Route path="tasks/:id" element={<Task />} />
        <Route path="pairs" element={<Pairs />} /><Route path="pairs/:id" element={<Compare />} />
        <Route path="*" element={<ErrorPage code={404} />} />
      </Routes>
    </PortalLayout>
  )
}
