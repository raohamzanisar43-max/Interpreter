import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errMsg, getLinkToken, iapi, setLinkToken } from '../../shared/api'
import AudioPlayer from '../../shared/AudioPlayer'
import { idbDel, idbGet, idbPut } from '../../shared/idb'
import { Button, Modal, Progress, Spinner, TextInput } from '../../shared/ui'
import { countdown, fmtDate, mmss } from '../../shared/util'
import { extFor, useRecorder } from './useRecorder'

function Shell({ children, back, title }) {
  return (
    <div className="i-shell">
      <div className="i-head">{back ? <Link to={back} className="btn sm">← Back</Link> : <strong style={{ color: 'var(--primary)', letterSpacing: '.06em' }}>EQAL</strong>}<span className="muted small">{title}</span></div>
      {children}
    </div>
  )
}

/** /i/:token — the secure link from the invitation email. */
export function EntryLink() {
  const { token } = useParams()
  const nav = useNavigate()
  const [err, setErr] = useState('')
  useEffect(() => {
    api.get(`/auth/token/${token}/`).then(() => { setLinkToken(token); nav('/interpret', { replace: true }) })
      .catch((e) => setErr(errMsg(e)))
  }, [token, nav])
  return <Shell>{err ? <div className="alert bad" role="alert">{err}<p><Link to="/interpret/link">Email me a new link</Link></p></div> : <div className="center"><Spinner /></div>}</Shell>
}

export function MagicLink() {
  const [email, setEmail] = useState('')
  const [done, setDone] = useState('')
  return (
    <Shell title="Sign in">
      <h1>Get your personal link</h1>
      <p className="muted">Enter the email address your company registered for you. If a round is open we will email you a secure link.</p>
      {done ? <div className="alert ok">{done}</div> : (
        <form onSubmit={async (e) => { e.preventDefault(); setDone((await api.post('/auth/magic-link/', { email })).data.message) }}>
          <TextInput label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button variant="primary" className="big" type="submit">Email me a link</Button>
        </form>
      )}
    </Shell>
  )
}

function useAssignment() {
  return useQuery({ queryKey: ['assignment'], queryFn: async () => (await iapi.get('/interpreter/assignment/')).data, retry: false, refetchOnWindowFocus: false })
}

function Gate({ children }) {
  const q = useAssignment()
  if (!getLinkToken()) return <Navigate to="/interpret/link" replace />
  if (q.isLoading) return <Shell><div className="center" style={{ padding: 40 }}><Spinner /></div></Shell>
  if (q.isError) {
    return <Shell><div className="alert bad" role="alert">{errMsg(q.error)}</div><Link className="btn big" to="/interpret/link">Email me a new link</Link></Shell>
  }
  return children(q.data)
}

function Entry({ a }) {
  if (a.status === 'submitted') return <Navigate to="/interpret/done" replace />
  const done = a.recordings.filter((r) => r.recorded).length
  return (
    <Shell>
      <div><p className="muted" style={{ marginBottom: 0 }}>Hello {a.interpreter_name.split(' ')[0]},</p><h1>{a.round_name}</h1></div>
      <div className="card"><p>Language: <strong>{a.language}</strong></p><p>Deadline: <strong>{fmtDate(a.deadline)}</strong><br /><span className="muted small">{countdown(a.deadline)}</span></p>
        {done > 0 && <><div className="row between small"><span>Progress</span><strong>{done}/{a.recordings.length} recorded</strong></div><Progress value={done} max={a.recordings.length} /></>}</div>
      {a.deadline_passed ? <div className="alert bad">The deadline for this round has passed. Please contact your company.</div>
        : <Link className="btn primary big" to="/interpret/instructions">{done ? 'Continue' : 'Start'}</Link>}
    </Shell>
  )
}

function Instructions({ a }) {
  const rec = useRecorder()
  const [playUrl, setPlayUrl] = useState(null)
  useEffect(() => { if (rec.result) { const u = URL.createObjectURL(rec.result.blob); setPlayUrl(u); return () => URL.revokeObjectURL(u) } return undefined }, [rec.result])
  return (
    <Shell back="/interpret" title={a.round_name}>
      <h1>Before you start</h1>
      <div className="card"><p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{a.instructions}</p></div>
      <div className="card stack">
        <h2>Microphone test</h2>
        <p className="muted small" style={{ margin: 0 }}>Tap, say something, then listen back.</p>
        {rec.error && <div className="alert bad" role="alert">{rec.error}</div>}
        <div className="meter" aria-label="Microphone level"><div style={{ width: `${rec.level * 100}%` }} /></div>
        {rec.state === 'recording' ? <Button className="big" variant="danger" onClick={rec.stop}>■ Stop ({rec.seconds}s)</Button> : <Button className="big" onClick={rec.start}>🎙 Say something</Button>}
        {playUrl && rec.state === 'stopped' && <audio controls src={playUrl} style={{ width: '100%' }} />}
      </div>
      <Link className="btn primary big" to="/interpret/list">Continue</Link>
    </Shell>
  )
}

function List({ a }) {
  const done = a.recordings.filter((r) => r.recorded).length
  return (
    <Shell back="/interpret/instructions" title={a.round_name}>
      <h1>Your recordings</h1>
      <div><div className="row between small"><span>{done} of {a.recordings.length} recorded</span></div><Progress value={done} max={a.recordings.length} /></div>
      {a.recordings.map((r, i) => (
        <Link key={r.id} to={`/interpret/record/${r.id}`} className="i-card" style={{ textDecoration: 'none' }}>
          <div><div className="muted small">Recording {i + 1}</div><strong>{r.title}</strong></div>
          <span className={`badge ${r.recorded ? 'ok' : ''}`}>{r.recorded ? '✓ Recorded' : 'Not started'}</span>
        </Link>
      ))}
      <Link className="btn primary big" to="/interpret/review" style={done === a.recordings.length ? undefined : { opacity: 0.6 }}>Review & submit</Link>
    </Shell>
  )
}

function RecordScreen({ a }) {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const rec = a.recordings.find((r) => String(r.id) === id)
  const R = useRecorder()
  const fileRef = useRef()
  const key = `take:${rec?.id}:${(getLinkToken() || '').slice(0, 12)}`
  const [pending, setPending] = useState(null)       // {blob, mime, seconds} awaiting upload
  const [localUrl, setLocalUrl] = useState(null)
  const [progress, setProgress] = useState(null)
  const [upErr, setUpErr] = useState('')
  const [warn, setWarn] = useState(false)
  const [busy, setBusy] = useState(false)

  // restore an unsent take from IndexedDB (network failure / page reload)
  useEffect(() => { idbGet(key).then((v) => { if (v?.blob) setPending(v) }) }, [key])
  useEffect(() => { if (R.result) setPending(R.result) }, [R.result])
  useEffect(() => { if (pending) { const u = URL.createObjectURL(pending.blob); setLocalUrl(u); return () => URL.revokeObjectURL(u) } setLocalUrl(null); return undefined }, [pending])
  // warn if the screen locks / the tab changes while recording
  useEffect(() => {
    const vis = () => { if (document.hidden && R.state === 'recording') setWarn(true) }
    const unload = (e) => { if (R.state === 'recording' || pending) { e.preventDefault(); e.returnValue = '' } }
    document.addEventListener('visibilitychange', vis); window.addEventListener('beforeunload', unload)
    return () => { document.removeEventListener('visibilitychange', vis); window.removeEventListener('beforeunload', unload) }
  }, [R.state, pending])

  if (!rec) return <Navigate to="/interpret/list" replace />
  const idx = a.recordings.findIndex((r) => r.id === rec.id)
  const locked = a.deadline_passed || a.status === 'submitted'

  const refreshSource = async () => { const d = (await qc.fetchQuery({ queryKey: ['assignment'], queryFn: async () => (await iapi.get('/interpreter/assignment/')).data, staleTime: 0 })); return d.recordings.find((r) => r.id === rec.id).source_audio_url }

  const keep = async (item = pending) => {
    setUpErr(''); setBusy(true); setProgress(0)
    await idbPut(key, item)                     // survive tab close / network loss until the server confirms
    try {
      const fd = new FormData()
      fd.append('file', item.blob, `take${extFor(item.mime)}`)
      if (item.seconds) fd.append('duration_sec', item.seconds)
      await iapi.post(`/interpreter/recordings/${rec.id}/take/`, fd, { onUploadProgress: (e) => setProgress(e.total ? Math.round((e.loaded / e.total) * 100) : null), timeout: 180000 })
      await idbDel(key); setPending(null); R.reset()
      await qc.invalidateQueries({ queryKey: ['assignment'] })
    } catch (e) { setUpErr(`${errMsg(e)} Your recording is saved on this device — tap Retry.`) } finally { setBusy(false); setProgress(null) }
  }
  const discard = async () => { await idbDel(key); setPending(null); R.reset() }
  const reRecord = async () => {
    if (rec.recorded) { try { await iapi.delete(`/interpreter/recordings/${rec.id}/take/`); await qc.invalidateQueries({ queryKey: ['assignment'] }) } catch (e) { setUpErr(errMsg(e)); return } }
    await discard(); setUpErr('')
  }
  const onFile = (e) => { const f = e.target.files[0]; if (f) setPending({ blob: f, mime: f.type || 'audio/mpeg', seconds: null }); e.target.value = '' }

  return (
    <Shell back="/interpret/list" title={`${idx + 1} of ${a.recordings.length}`}>
      <h1>{rec.title}</h1>
      {locked && <div className="alert bad">{a.status === 'submitted' ? 'Already submitted.' : 'The deadline has passed.'}</div>}
      <AudioPlayer url={rec.source_audio_url} label="1. Listen to the original" refresh={refreshSource} singlePlay={!a.allow_replay} />
      <div className="card stack">
        <h2>2. Your interpretation</h2>
        {warn && R.state === 'recording' && <div className="alert warn" role="alert">The page was in the background. Some phones pause recording when the screen locks — check your take after stopping.</div>}
        {R.error && <div className="alert bad" role="alert">{R.error}</div>}
        {upErr && <div className="alert bad" role="alert">{upErr}</div>}

        {rec.recorded && !pending && (<>
          <div className="alert ok">✓ Saved{rec.take_duration ? ` (${mmss(rec.take_duration)})` : ''}</div>
          <AudioPlayer url={rec.take_url} label="Your saved take" compact />
          {!locked && <Button className="big" onClick={reRecord}>↺ Re-record</Button>}
        </>)}

        {!rec.recorded && !pending && R.state !== 'recording' && !locked && (<>
          <div className="meter" aria-label="Microphone level"><div style={{ width: '0%' }} /></div>
          <button type="button" className="rec-btn" onClick={R.start} aria-label="Start recording">● Record</button>
          <Button onClick={() => fileRef.current.click()}>⬆ Upload audio file instead</Button>
          <input ref={fileRef} type="file" accept="audio/*" hidden onChange={onFile} />
        </>)}

        {R.state === 'recording' && (<>
          <div className="timer" aria-live="off">{mmss(R.seconds)}</div>
          <div className="meter" aria-label="Microphone level"><div style={{ width: `${R.level * 100}%` }} /></div>
          <button type="button" className="rec-btn recording" onClick={R.stop} aria-label="Stop recording">■ Stop</button>
        </>)}

        {pending && R.state !== 'recording' && (<>
          <audio controls src={localUrl} style={{ width: '100%' }} />
          {progress !== null && <><div className="row between small"><span>Uploading…</span><strong>{progress}%</strong></div><Progress value={progress} max={100} /></>}
          <div className="grid2">
            <Button className="big" onClick={reRecord} disabled={busy}>↺ Re-record</Button>
            <Button className="big" variant="primary" onClick={() => keep()} disabled={busy || locked}>{busy ? <Spinner /> : upErr ? '↻ Retry upload' : '✓ Keep'}</Button>
          </div>
        </>)}
      </div>
      <div className="grid2">
        {idx > 0 ? <Link className="btn big" to={`/interpret/record/${a.recordings[idx - 1].id}`}>← Previous</Link> : <span />}
        {idx < a.recordings.length - 1 ? <Link className="btn big" to={`/interpret/record/${a.recordings[idx + 1].id}`}>Next →</Link> : <Link className="btn primary big" to="/interpret/review">Review</Link>}
      </div>
    </Shell>
  )
}

function Review({ a }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [confirm, setConfirm] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const allDone = a.recordings.every((r) => r.recorded)
  const submit = async () => {
    setBusy(true); setErr('')
    try { await iapi.post('/interpreter/assignment/submit/'); await qc.invalidateQueries({ queryKey: ['assignment'] }); nav('/interpret/done', { replace: true }) } catch (e) { setErr(errMsg(e)); setConfirm(false) } finally { setBusy(false) }
  }
  return (
    <Shell back="/interpret/list" title={a.round_name}>
      <h1>Review & submit</h1>
      {err && <div className="alert bad" role="alert">{err}</div>}
      <div className="card stack">{a.recordings.map((r) => (
        <div key={r.id} className="row between"><span>{r.recorded ? '✅' : '⬜'} {r.title}</span>{!a.deadline_passed && <Link to={`/interpret/record/${r.id}`} className="small">{r.recorded ? 'Change' : 'Record'}</Link>}</div>
      ))}</div>
      {!allDone && <div className="alert warn">Record every item before you can submit.</div>}
      <Button className="big" variant="primary" disabled={!allDone || a.deadline_passed} onClick={() => setConfirm(true)}>Submit</Button>
      {confirm && <Modal title="Submit your recordings?" onClose={() => setConfirm(false)} actions={<><Button onClick={() => setConfirm(false)}>Not yet</Button><Button variant="primary" disabled={busy} onClick={submit}>{busy ? <Spinner /> : 'Yes, submit'}</Button></>}>
        <p>After you submit <strong>no changes are possible</strong>. You will receive a confirmation email.</p></Modal>}
    </Shell>
  )
}

function Done({ a }) {
  return (
    <Shell>
      <div className="card center"><div style={{ fontSize: '3rem' }}>✅</div><h1>Submitted</h1><p>Thank you{a.interpreter_name ? `, ${a.interpreter_name.split(' ')[0]}` : ''}. Your recordings for <strong>{a.round_name}</strong> were received{a.submitted_at ? ` on ${fmtDate(a.submitted_at)}` : ''}. A receipt has been emailed to you.</p>
        <p className="muted small">Your recordings are assessed anonymously. You will not see scores; your company receives an aggregated report.</p></div>
    </Shell>
  )
}

export default function InterpreterApp() {
  return (
    <Routes>
      <Route index element={<Gate>{(a) => <Entry a={a} />}</Gate>} />
      <Route path="instructions" element={<Gate>{(a) => <Instructions a={a} />}</Gate>} />
      <Route path="list" element={<Gate>{(a) => <List a={a} />}</Gate>} />
      <Route path="record/:id" element={<Gate>{(a) => <RecordScreen a={a} />}</Gate>} />
      <Route path="review" element={<Gate>{(a) => <Review a={a} />}</Gate>} />
      <Route path="done" element={<Gate>{(a) => <Done a={a} />}</Gate>} />
      <Route path="link" element={<MagicLink />} />
      <Route path="*" element={<Navigate to="/interpret" replace />} />
    </Routes>
  )
}
