import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { api, errMsg, fieldErrors } from '../../shared/api'
import AudioPlayer from '../../shared/AudioPlayer'
import { useAction, useGet } from '../../shared/hooks'
import { Badge, Button, Card, Empty, Query, Spinner, StatusBadge, Table, TextInput, useToast } from '../../shared/ui'
import { fmtDate, mmss, toLocalInput } from '../../shared/util'

const STATUSES = ['', 'draft', 'open', 'closed', 'rating', 'review', 'released', 'archived']

export function RoundsList() {
  const nav = useNavigate()
  const [status, setStatus] = useState('')
  const q = useGet(`/admin/rounds/${status ? `?status=${status}` : ''}`)
  return (
    <div className="stack">
      <div className="page-head"><h1>Rounds</h1>
        <div className="row"><select aria-label="Filter by status" style={{ width: 170 }} value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{s || 'All statuses'}</option>)}</select>
          <Link className="btn primary" to="/admin/rounds/new">+ New round</Link></div></div>
      <Query q={q}>{(rows) => (
        <Table empty="No rounds match." rows={rows} onRow={(r) => nav(`/admin/rounds/${r.id}`)} columns={[
          { label: 'Round', render: (r) => <Link to={`/admin/rounds/${r.id}`} onClick={(e) => e.stopPropagation()}><strong>{r.name}</strong></Link> },
          { label: 'Language', key: 'language' }, { label: 'Deadline', render: (r) => fmtDate(r.deadline) },
          { label: 'Status', render: (r) => <StatusBadge status={r.status} /> },
          { label: 'Companies', key: 'companies_count' }, { label: 'Recordings', key: 'recordings_count' },
          { label: 'Submitted', render: (r) => `${r.submitted}/${r.assignments_total}` },
        ]} />
      )}</Query>
    </div>
  )
}

/** Key points editor for one recording (used in wizard step 4 and in the round detail "Answer key" tab). */
export function KeyPointsEditor({ recording, locked, onChanged }) {
  const { toast, confirm } = useToast()
  const [dragFrom, setDragFrom] = useState(null)
  const [over, setOver] = useState(null)
  const [draft, setDraft] = useState({ text: '', category: 'other', weight: 1, admin_notes: '' })
  const [notes, setNotes] = useState(null)
  const kps = recording.key_points

  const add = async (e) => {
    e.preventDefault()
    try { await api.post(`/admin/recordings/${recording.id}/keypoints/`, draft); setDraft({ ...draft, text: '', admin_notes: '' }); onChanged() } catch (er) { toast.error(er) }
  }
  const patch = async (id, body) => { try { await api.patch(`/admin/keypoints/${id}/`, body); onChanged() } catch (er) { toast.error(er) } }
  const del = async (id) => { if (!(await confirm({ message: 'Delete this key point?', danger: true }))) return; try { await api.delete(`/admin/keypoints/${id}/`); onChanged() } catch (er) { toast.error(er) } }
  const drop = async (to) => {
    if (dragFrom === null || dragFrom === to) return
    const ids = kps.map((k) => k.id); const [m] = ids.splice(dragFrom, 1); ids.splice(to, 0, m)
    setDragFrom(null); setOver(null)
    try { await api.post(`/admin/recordings/${recording.id}/keypoints/reorder/`, { ids }); onChanged() } catch (er) { toast.error(er) }
  }

  return (
    <div className="stack">
      {recording.audio_url && <AudioPlayer url={recording.audio_url} label="Source recording" />}
      <div className="field"><label htmlFor={`tr-${recording.id}`}>Transcript (admin only)</label>
        <textarea id={`tr-${recording.id}`} defaultValue={recording.transcript} disabled={locked} onBlur={(e) => e.target.value !== recording.transcript && api.patch(`/admin/recordings/${recording.id}/`, { transcript: e.target.value }).then(onChanged).catch(toast.error)} /></div>
      <h3>Key points {kps.length === 0 && <Badge tone="warn">needs at least one</Badge>}</h3>
      {kps.length > 0 && (
        <div className="table-wrap"><table><thead><tr><th /><th>Text</th><th>Category</th><th>Weight</th><th>Notes (admin only)</th><th /></tr></thead><tbody>
          {kps.map((k, i) => (
            <tr key={k.id} draggable={!locked} className={`dragrow ${over === i ? 'over' : ''}`}
              onDragStart={() => setDragFrom(i)} onDragOver={(e) => { e.preventDefault(); setOver(i) }} onDrop={() => drop(i)} onDragEnd={() => { setDragFrom(null); setOver(null) }}>
              <td aria-hidden="true" title="Drag to reorder">⋮⋮</td>
              <td><input defaultValue={k.text} disabled={locked} aria-label="Key point text" onBlur={(e) => e.target.value !== k.text && patch(k.id, { text: e.target.value })} /></td>
              <td><select defaultValue={k.category} disabled={locked} aria-label="Category" onChange={(e) => patch(k.id, { category: e.target.value })}>{['warning', 'doubt', 'dosage', 'instruction', 'other'].map((c) => <option key={c}>{c}</option>)}</select></td>
              <td style={{ width: 80 }}><input type="number" min="0.1" step="0.5" defaultValue={k.weight} disabled={locked} aria-label="Weight" onBlur={(e) => Number(e.target.value) !== k.weight && patch(k.id, { weight: e.target.value })} /></td>
              <td><input defaultValue={k.admin_notes} disabled={locked} aria-label="Admin notes" onBlur={(e) => e.target.value !== k.admin_notes && patch(k.id, { admin_notes: e.target.value })} /></td>
              <td>{!locked && <Button size="sm" onClick={() => del(k.id)} aria-label="Delete key point">✕</Button>}</td>
            </tr>
          ))}
        </tbody></table></div>
      )}
      {!locked && (
        <form onSubmit={add} className="row" style={{ alignItems: 'flex-end' }}>
          <div style={{ flex: '3 1 260px' }}><TextInput label="New key point" required value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} /></div>
          <div style={{ flex: '1 1 130px' }}><div className="field"><label htmlFor="nkp-cat">Category</label><select id="nkp-cat" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>{['warning', 'doubt', 'dosage', 'instruction', 'other'].map((c) => <option key={c}>{c}</option>)}</select></div></div>
          <div style={{ flex: '0 1 90px' }}><TextInput label="Weight" type="number" min="0.1" step="0.5" value={draft.weight} onChange={(e) => setDraft({ ...draft, weight: e.target.value })} /></div>
          <div style={{ marginBottom: 12 }}><Button variant="primary" type="submit">Add</Button></div>
        </form>
      )}
    </div>
  )
}

const STEPS = ['Basics', 'Companies', 'Recordings', 'Answer key', 'Review & open']

export function RoundWizard() {
  const { id: editId } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { toast } = useToast()
  const companies = useGet('/admin/companies/')
  const settings = useGet('/admin/settings/')
  const [step, setStep] = useState(0)
  const [round, setRound] = useState(null)       // created after step 1
  const [form, setForm] = useState({ name: '', language: '', deadline: toLocalInput(Date.now() + 14 * 864e5), retention_days: '', instructions: '' })
  const [chosen, setChosen] = useState([])
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)
  const [uploading, setUploading] = useState(0)
  const [selRec, setSelRec] = useState(null)
  const fileRef = useRef()
  const dragFrom = useRef(null)

  useEffect(() => {          // resume editing an existing draft
    if (!editId) return
    api.get(`/admin/rounds/${editId}/`).then(({ data: r }) => {
      setRound(r); setChosen(r.companies.map((c) => c.id))
      setForm({ name: r.name, language: r.language, deadline: toLocalInput(r.deadline), retention_days: r.retention_days, instructions: r.instructions })
    }).catch(toast.error)
  }, [editId]) // eslint-disable-line react-hooks/exhaustive-deps

  const reload = async (id = round.id) => { const r = (await api.get(`/admin/rounds/${id}/`)).data; setRound(r); qc.invalidateQueries({ queryKey: ['/admin/rounds/'] }); return r }

  const createRound = async () => {
    setErrs({}); setBusy(true)
    try {
      const body = { ...form, deadline: new Date(form.deadline).toISOString(), retention_days: form.retention_days || settings.data?.default_retention_days }
      if (!form.instructions) delete body.instructions
      if (round) { await api.patch(`/admin/rounds/${round.id}/`, body); await reload(); setStep(1) }
      else { const r = (await api.post('/admin/rounds/', body)).data; setRound(r); setStep(1) }
    } catch (e) { setErrs(fieldErrors(e)); toast.error(e) } finally { setBusy(false) }
  }
  const saveCompanies = async () => {
    if (!chosen.length) return toast.error('Select at least one company.')
    setBusy(true)
    try { await api.patch(`/admin/rounds/${round.id}/`, { company_ids: chosen }); await reload(); setStep(2) } catch (e) { toast.error(e) } finally { setBusy(false) }
  }
  const upload = async (files) => {
    for (const f of files) {
      setUploading((n) => n + 1)
      try { const fd = new FormData(); fd.append('file', f); fd.append('title', f.name.replace(/\.[^.]+$/, '')); await api.post(`/admin/rounds/${round.id}/recordings/`, fd) } catch (e) { toast.error(`${f.name}: ${errMsg(e)}`) }
      setUploading((n) => n - 1)
    }
    await reload()
  }
  const reorder = async (to) => {
    const from = dragFrom.current; if (from === null || from === to) return
    const ids = round.recordings.map((r) => r.id); const [m] = ids.splice(from, 1); ids.splice(to, 0, m); dragFrom.current = null
    await api.post(`/admin/rounds/${round.id}/recordings/reorder/`, { ids }); await reload()
  }
  const open = async () => {
    setBusy(true)
    try { await api.post(`/admin/rounds/${round.id}/open/`); toast('Round opened — invitations sent.'); qc.invalidateQueries(); nav(`/admin/rounds/${round.id}`) } catch (e) { toast.error(e) } finally { setBusy(false) }
  }
  const missing = round ? round.recordings.filter((r) => r.key_points.length === 0).map((r) => r.title) : []

  return (
    <div className="stack">
      <div className="page-head"><h1>{round ? `Draft: ${round.name}` : 'New round'}</h1>{round && <Link className="btn" to={`/admin/rounds/${round.id}`}>Save draft & exit</Link>}</div>
      <div className="steps" aria-label="Progress">{STEPS.map((s, i) => <span key={s} className={`step ${i === step ? 'on' : i < step ? 'done' : ''}`}>{i + 1}. {s}</span>)}</div>

      {step === 0 && (
        <Card title="Basics"><form onSubmit={(e) => { e.preventDefault(); createRound() }}>
          <TextInput label="Round name" required value={form.name} error={errs.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <div className="grid2">
            <TextInput label="Language" required hint="Raters are matched on this exactly, e.g. Urdu" value={form.language} error={errs.language} onChange={(e) => setForm({ ...form, language: e.target.value })} />
            <TextInput label="Deadline" type="datetime-local" required value={form.deadline} error={errs.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
          </div>
          <TextInput label="Retention (days)" type="number" min="1" hint={`Audio is deleted this many days after the deadline. Default ${settings.data?.default_retention_days ?? 90}.`} value={form.retention_days} onChange={(e) => setForm({ ...form, retention_days: e.target.value })} />
          <div className="field"><label htmlFor="instr">Instructions for interpreters</label><textarea id="instr" placeholder="Leave empty for the default text" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} /></div>
          <Button variant="primary" type="submit" disabled={busy}>{busy ? <Spinner /> : 'Next →'}</Button>
        </form></Card>
      )}

      {step === 1 && (
        <Card title="Participating companies"><Query q={companies}>{(rows) => (
          <div className="stack">
            {rows.filter((c) => c.status === 'active').map((c) => (
              <label key={c.id} className="row"><input type="checkbox" checked={chosen.includes(c.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, c.id] : chosen.filter((x) => x !== c.id))} /> <strong>{c.name}</strong> <span className="muted small">{c.interpreters_count} interpreters</span></label>
            ))}
            {rows.length === 0 && <Empty>No companies yet — add some first.</Empty>}
            <p className="muted small">Interpreters receive their secure link when the round opens. Rankings are hidden for rounds with fewer than 3 companies.</p>
            <div className="row"><Button onClick={() => setStep(0)}>← Back</Button><Button variant="primary" onClick={saveCompanies} disabled={busy}>Next →</Button></div>
          </div>
        )}</Query></Card>
      )}

      {step === 2 && round && (
        <Card title="Source recordings">
          <div className={`drop ${over ? 'over' : ''}`} onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); upload([...e.dataTransfer.files]) }}>
            <p>Drag & drop audio here (mp3, wav, m4a, ogg, webm)</p>
            <input ref={fileRef} type="file" accept="audio/*" multiple hidden onChange={(e) => { upload([...e.target.files]); e.target.value = '' }} />
            <Button onClick={() => fileRef.current.click()}>Choose files</Button> {uploading > 0 && <Spinner />}
          </div>
          <div className="stack" style={{ marginTop: 14 }}>
            {round.recordings.map((r, i) => (
              <div key={r.id} className="card dragrow" draggable onDragStart={() => { dragFrom.current = i }} onDragOver={(e) => e.preventDefault()} onDrop={() => reorder(i)}>
                <div className="row between"><div className="row"><span aria-hidden="true">⋮⋮</span><strong>{i + 1}.</strong>
                  <input style={{ width: 280 }} defaultValue={r.title} aria-label="Recording title" onBlur={(e) => e.target.value !== r.title && api.patch(`/admin/recordings/${r.id}/`, { title: e.target.value }).then(() => reload())} />
                  <span className="muted small">{r.duration_sec ? mmss(r.duration_sec) : ''}</span></div>
                  <Button size="sm" onClick={async () => { await api.delete(`/admin/recordings/${r.id}/`); reload() }}>Remove</Button></div>
                <AudioPlayer url={r.audio_url} compact />
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 14 }}><Button onClick={() => setStep(1)}>← Back</Button><Button variant="primary" disabled={!round.recordings.length} onClick={() => { setSelRec(round.recordings[0]?.id); setStep(3) }}>Next →</Button></div>
        </Card>
      )}

      {step === 3 && round && (
        <Card title="Answer key">
          <div className="tabs">{round.recordings.map((r) => <button key={r.id} className={selRec === r.id ? 'active' : ''} onClick={() => setSelRec(r.id)}>{r.title} {r.key_points.length === 0 && '⚠'}</button>)}</div>
          {round.recordings.filter((r) => r.id === selRec).map((r) => <KeyPointsEditor key={r.id} recording={r} onChanged={reload} />)}
          <div className="row" style={{ marginTop: 14 }}><Button onClick={() => setStep(2)}>← Back</Button><Button variant="primary" onClick={() => setStep(4)}>Next →</Button></div>
        </Card>
      )}

      {step === 4 && round && (
        <Card title="Review & open">
          <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 6 }}>
            <dt className="muted">Name</dt><dd>{round.name}</dd><dt className="muted">Language</dt><dd>{round.language}</dd>
            <dt className="muted">Deadline</dt><dd>{fmtDate(round.deadline)}</dd><dt className="muted">Retention</dt><dd>{round.retention_days} days</dd>
            <dt className="muted">Companies</dt><dd>{round.companies.map((c) => c.name).join(', ')}</dd>
            <dt className="muted">Recordings</dt><dd>{round.recordings.map((r) => `${r.title} (${r.key_points.length} key points)`).join(' · ')}</dd>
          </dl>
          {missing.length > 0 && <div className="alert warn">Recordings without key points: {missing.join(', ')}</div>}
          <div className="alert">Opening the round creates a secure link for every active interpreter of the selected companies and emails it to them.</div>
          <div className="row"><Button onClick={() => setStep(3)}>← Back</Button><Button variant="primary" disabled={busy || missing.length > 0} onClick={open}>{busy ? <Spinner /> : 'Open round & send invitations'}</Button></div>
        </Card>
      )}
    </div>
  )
}
