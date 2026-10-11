import { useRef, useState } from 'react'
import { api, download, errMsg } from '../../shared/api'
import AudioPlayer from '../../shared/AudioPlayer'
import { useAction, useGet } from '../../shared/hooks'
import { Badge, Button, Card, Modal, Query, Table, Tabs, TextInput, useToast } from '../../shared/ui'
import { fmtDate, mdToHtml } from '../../shared/util'

// ------------------------------------------------------------------ practice items
export function Practice() {
  const q = useGet('/admin/practice/')
  const { toast, confirm } = useToast()
  const [form, setForm] = useState(null)
  const [kp, setKp] = useState({})
  const src = useRef(); const intr = useRef()
  const create = useAction(async (f) => {
    const fd = new FormData()
    fd.append('title', f.title); fd.append('language', f.language)
    if (src.current?.files[0]) fd.append('source_file', src.current.files[0])
    if (intr.current?.files[0]) fd.append('interpretation_file', intr.current.files[0])
    return api.post('/admin/practice/', fd)
  }, { invalidate: ['/admin/practice/'], success: 'Practice item created — add key points below.', onSuccess: () => setForm(null) })
  const addKp = async (id) => {
    const k = kp[id]; if (!k?.text) return
    try { await api.post(`/admin/practice/${id}/keypoints/`, { reference_value: 'full', ...k }); setKp({ ...kp, [id]: { text: '', reference_value: 'full', explanation: '' } }); q.refetch() } catch (e) { toast.error(e) }
  }
  return (
    <div className="stack">
      <div className="page-head"><h1>Practice items</h1><Button variant="primary" onClick={() => setForm({ title: '', language: '' })}>+ New practice item</Button></div>
      <p className="muted">Raters score these first and compare with your reference values. Real tasks stay locked until they reach the calibration threshold (see Settings).</p>
      <Query q={q}>{(rows) => rows.length === 0 ? <Card><p className="muted">No practice items — raters are not required to calibrate.</p></Card> : rows.map((p) => (
        <Card key={p.id} title={p.title} actions={<><Badge tone={p.active ? 'ok' : ''}>{p.active ? 'active' : 'inactive'}</Badge><Button size="sm" onClick={async () => { await api.patch(`/admin/practice/${p.id}/`, { active: !p.active }); q.refetch() }}>{p.active ? 'Deactivate' : 'Activate'}</Button>
          <Button size="sm" onClick={async () => { if (await confirm({ message: 'Delete this practice item?', danger: true })) { await api.delete(`/admin/practice/${p.id}/`); q.refetch() } }}>Delete</Button></>}>
          <div className="split">{p.source_audio_url && <AudioPlayer url={p.source_audio_url} label="Original" />}{p.interpretation_audio_url && <AudioPlayer url={p.interpretation_audio_url} label="Interpretation" />}</div>
          <Table empty="No key points yet." rows={p.key_points} columns={[{ label: 'Key point', key: 'text' }, { label: 'Reference', render: (k) => <Badge tone={k.reference_value === 'full' ? 'ok' : k.reference_value === 'partial' ? 'warn' : 'bad'}>{k.reference_value}</Badge> }, { label: 'Explanation', key: 'explanation' },
            { label: '', render: (k) => <Button size="sm" onClick={async () => { await api.delete(`/admin/practice-keypoints/${k.id}/`); q.refetch() }}>✕</Button> }]} />
          <div className="row" style={{ marginTop: 10, alignItems: 'flex-end' }}>
            <div style={{ flex: '3 1 220px' }}><TextInput label="Key point" value={kp[p.id]?.text || ''} onChange={(e) => setKp({ ...kp, [p.id]: { ...kp[p.id], text: e.target.value } })} /></div>
            <div style={{ flex: '0 1 130px' }}><div className="field"><label>Reference</label><select aria-label="Reference value" value={kp[p.id]?.reference_value || 'full'} onChange={(e) => setKp({ ...kp, [p.id]: { ...kp[p.id], reference_value: e.target.value } })}><option value="full">full</option><option value="partial">partial</option><option value="lost">lost</option></select></div></div>
            <div style={{ flex: '2 1 200px' }}><TextInput label="Explanation" value={kp[p.id]?.explanation || ''} onChange={(e) => setKp({ ...kp, [p.id]: { ...kp[p.id], explanation: e.target.value } })} /></div>
            <div style={{ marginBottom: 12 }}><Button onClick={() => addKp(p.id)}>Add</Button></div>
          </div>
        </Card>
      ))}</Query>
      {form && (
        <Modal title="New practice item" onClose={() => setForm(null)} actions={<><Button onClick={() => setForm(null)}>Cancel</Button><Button variant="primary" disabled={!form.title} onClick={() => create.mutate(form)}>Create</Button></>}>
          <TextInput label="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <TextInput label="Language" value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })} />
          <div className="field"><label htmlFor="ps">Original audio</label><input id="ps" ref={src} type="file" accept="audio/*" /></div>
          <div className="field"><label htmlFor="pi">Sample interpretation audio</label><input id="pi" ref={intr} type="file" accept="audio/*" /></div>
        </Modal>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ exports
export function Exports() {
  const rounds = useGet('/admin/rounds/')
  const { toast } = useToast()
  const [rid, setRid] = useState('')
  const [history, setHistory] = useState(() => { try { return JSON.parse(localStorage.getItem('eqal_exports')) || [] } catch { return [] } })
  const run = async (url, name) => {
    try { await download(url, name); const h = [{ name, at: new Date().toISOString() }, ...history].slice(0, 15); setHistory(h); localStorage.setItem('eqal_exports', JSON.stringify(h)); toast('Export downloaded (logged in the audit trail).') } catch (e) { toast.error(e) }
  }
  return (
    <div className="stack">
      <h1>Exports</h1>
      <Card title="Excel workbook">
        <p className="muted">Sheets: Rounds, Companies, Interpreters, Recordings & Key points, Raw checklist scores, Pairwise, Company aggregates, Audit summary. Contains identities — handle with care. Every export is audit-logged.</p>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <div style={{ minWidth: 260 }}><div className="field"><label htmlFor="exr">Round</label><select id="exr" value={rid} onChange={(e) => setRid(e.target.value)}><option value="">Select a round…</option>{(rounds.data || []).map((r) => <option key={r.id} value={r.id}>{r.name} ({r.status})</option>)}</select></div></div>
          <div style={{ marginBottom: 12 }} className="row"><Button variant="primary" disabled={!rid} onClick={() => run(`/admin/rounds/${rid}/export.xlsx`, `eqal-round-${rid}.xlsx`)}>Export round</Button><Button onClick={() => run('/admin/export/all.xlsx', 'eqal-full-export.xlsx')}>Export everything</Button></div>
        </div>
      </Card>
      <Card title="Download history (this browser)"><Table empty="No exports yet." rows={history.map((h, i) => ({ ...h, id: i }))} columns={[{ label: 'File', key: 'name' }, { label: 'When', render: (h) => fmtDate(h.at) }]} /></Card>
    </div>
  )
}

// ------------------------------------------------------------------ audit log
export function Audit() {
  const [f, setF] = useState({ actor: '', action: '', date_from: '', date_to: '' })
  const [open, setOpen] = useState(null)
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const q = useGet(`/admin/audit/?${qs}`)
  const { toast } = useToast()
  return (
    <div className="stack">
      <div className="page-head"><h1>Audit log</h1><Button onClick={() => download(`/admin/audit/?${qs}${qs ? '&' : ''}export=csv`, 'audit-log.csv').catch(toast.error)}>Export CSV</Button></div>
      <Card><div className="row" style={{ alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 180px' }}><TextInput label="Actor" value={f.actor} onChange={(e) => setF({ ...f, actor: e.target.value })} /></div>
        <div style={{ flex: '1 1 180px' }}><div className="field"><label htmlFor="aa">Action</label><select id="aa" value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })}><option value="">All</option>{(q.data?.actions || []).map((a) => <option key={a}>{a}</option>)}</select></div></div>
        <div style={{ flex: '1 1 150px' }}><TextInput label="From" type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></div>
        <div style={{ flex: '1 1 150px' }}><TextInput label="To" type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></div>
      </div></Card>
      <Query q={q}>{(d) => (<><p className="muted small">{d.total} entries{d.total > d.results.length ? ` (showing ${d.results.length})` : ''}</p>
        <Table rows={d.results} onRow={setOpen} columns={[{ label: 'Time', render: (a) => fmtDate(a.timestamp) }, { label: 'Actor', key: 'actor' }, { label: 'Action', render: (a) => <Badge>{a.action}</Badge> }, { label: 'Object', render: (a) => (a.object_type ? `${a.object_type} #${a.object_id}` : '—') }, { label: 'IP', key: 'ip' }]} /></>)}</Query>
      {open && <Modal title="Audit entry" onClose={() => setOpen(null)} actions={<Button onClick={() => setOpen(null)}>Close</Button>}>
        <dl style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: 6 }}><dt className="muted">Time</dt><dd>{fmtDate(open.timestamp)}</dd><dt className="muted">Actor</dt><dd>{open.actor}</dd><dt className="muted">Action</dt><dd>{open.action}</dd><dt className="muted">Object</dt><dd>{open.object_type} {open.object_id}</dd><dt className="muted">IP</dt><dd>{open.ip || '—'}</dd></dl>
        <pre style={{ background: 'var(--surface-2)', padding: 10, borderRadius: 8, overflow: 'auto' }}>{JSON.stringify(open.metadata, null, 2)}</pre></Modal>}
    </div>
  )
}

// ------------------------------------------------------------------ data protection (erasure / access requests)
export function DataProtection() {
  const [search, setSearch] = useState('')
  const q = useGet(`/admin/interpreters/?q=${encodeURIComponent(search)}`)
  const { toast, confirm } = useToast()
  const history = useGet('/admin/audit/?action=erasure')
  const del = useGet('/admin/audit/?action=deletion')
  const act = async (i, action, msg, danger) => {
    if (!(await confirm({ message: msg, danger, confirmLabel: 'Proceed' }))) return
    if (danger && !(await confirm({ title: 'Please confirm again', message: `This is permanent. Proceed with "${action}" for ${i.full_name}?`, danger: true }))) return
    try { await api.post(`/admin/interpreters/${i.id}/${action}/`, { confirm: true }); toast('Done — recorded in the audit log.'); q.refetch(); history.refetch(); del.refetch() } catch (e) { toast.error(e) }
  }
  const exportData = async (i) => {
    try { const d = (await api.get(`/admin/interpreters/${i.id}/export/`)).data; const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' })); a.download = `subject-access-${i.id}.json`; a.click() } catch (e) { toast.error(errMsg(e)) }
  }
  return (
    <div className="stack">
      <h1>Data protection</h1>
      <Card title="Interpreter data requests">
        <p className="muted">Export everything held about an interpreter (access request), delete their audio, or erase them entirely (name + email anonymised, audio deleted, links revoked; anonymous scores remain).</p>
        <input placeholder="Search name, email or company…" aria-label="Search interpreters" value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginBottom: 10, maxWidth: 360 }} />
        <Query q={q}>{(rows) => <Table rows={rows} columns={[{ label: 'Interpreter', render: (i) => <>{i.full_name}<div className="muted small">{i.email}</div></> }, { label: 'Company', key: 'company' }, { label: 'State', render: (i) => (i.erased ? <Badge tone="bad">erased</Badge> : i.is_active ? <Badge tone="ok">active</Badge> : <Badge>inactive</Badge>) },
          { label: '', render: (i) => !i.erased && <div className="row"><Button size="sm" onClick={() => exportData(i)}>Export data</Button><Button size="sm" onClick={() => act(i, 'delete-audio', `Delete all audio for ${i.full_name}?`, true)}>Delete audio</Button><Button size="sm" variant="danger" onClick={() => act(i, 'erase', `Erase ${i.full_name}'s personal data?`, true)}>Erase</Button></div> }]} />}</Query>
      </Card>
      <Card title="Deletion history"><Query q={del}>{(d) => <Table empty="No deletions recorded." rows={[...(history.data?.results || []), ...d.results].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))} columns={[{ label: 'When', render: (a) => fmtDate(a.timestamp) }, { label: 'Actor', key: 'actor' }, { label: 'Type', key: 'action' }, { label: 'Object', render: (a) => `${a.object_type} #${a.object_id}` }, { label: 'Certificate', render: (a) => a.metadata.certificate || a.metadata.scope || '' }, { label: 'Files', render: (a) => a.metadata.files_deleted ?? '' }]} />}</Query></Card>
    </div>
  )
}

// ------------------------------------------------------------------ rater analytics
export function RaterAnalytics() {
  const q = useGet('/admin/rater-analytics/')
  return (
    <div className="stack">
      <h1>Rater quality</h1>
      <p className="muted">Agreement is measured against the other raters scoring the same items. Low agreement or very short scoring times are worth a conversation.</p>
      <Query q={q}>{(rows) => <Table empty="No raters." rows={rows.map((r) => ({ ...r, id: r.rater_id }))} columns={[
        { label: 'Rater', key: 'email' }, { label: 'Done', render: (r) => `${r.tasks_done}/${r.tasks_total}` },
        { label: 'Same as panel', render: (r) => (r.pct_same_as_panel === null ? '—' : `${r.pct_same_as_panel}%`) },
        { label: 'Mean diff (pts)', render: (r) => r.mean_abs_diff ?? '—' }, { label: 'Avg minutes / item', render: (r) => r.avg_minutes ?? '—' },
        { label: 'Practice accuracy', render: (r) => (r.practice_accuracy === null ? '—' : `${r.practice_accuracy}%`) },
        { label: 'Calibrated', render: (r) => <Badge tone={r.is_calibrated ? 'ok' : 'warn'}>{r.is_calibrated ? 'yes' : 'no'}</Badge> }, { label: 'Excluded', key: 'excluded_tasks' }]} />}</Query>
    </div>
  )
}

// ------------------------------------------------------------------ settings
export function Settings() {
  const [tab, setTab] = useState('general')
  return (
    <div className="stack">
      <h1>Settings</h1>
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'general', label: 'General' }, { key: 'terms', label: 'Terms' }, { key: 'privacy', label: 'Privacy notice' }, { key: 'email', label: 'Email templates' }, { key: 'log', label: 'Sent emails' }]} />
      {tab === 'general' && <General />}
      {tab === 'terms' && <Versioned kind="terms" title="Terms" note="Publishing a new version makes every company re-accept before continuing." />}
      {tab === 'privacy' && <Versioned kind="privacy" title="Privacy notice" note="Shown publicly at /privacy." />}
      {tab === 'email' && <Templates />}
      {tab === 'log' && <EmailLog />}
    </div>
  )
}

function General() {
  const q = useGet('/admin/settings/')
  const [f, setF] = useState(null)
  const save = useAction(async (v) => (await api.patch('/admin/settings/', v)).data, { invalidate: ['/admin/settings/'], success: 'Settings saved.' })
  const v = f || q.data
  const set = (k, val) => setF({ ...v, [k]: val })
  return (
    <Query q={q}>{() => (
      <Card title="General"><form onSubmit={(e) => { e.preventDefault(); save.mutate(v) }}>
        <div className="grid2">
          <TextInput label="Default retention (days)" type="number" min="1" value={v.default_retention_days} onChange={(e) => set('default_retention_days', e.target.value)} />
          <TextInput label="Reminder schedule (days before deadline)" hint="Comma separated, e.g. 7,3,1" value={v.reminder_days} onChange={(e) => set('reminder_days', e.target.value)} />
          <TextInput label="Idle timeout (minutes, admin & rater)" type="number" min="1" value={v.idle_timeout_minutes} onChange={(e) => set('idle_timeout_minutes', e.target.value)} />
          <TextInput label="Calibration threshold (%)" type="number" min="0" max="100" value={v.calibration_threshold} onChange={(e) => set('calibration_threshold', e.target.value)} />
          <TextInput label="Disagreement threshold (score spread, points)" type="number" min="0" value={v.disagreement_threshold} onChange={(e) => set('disagreement_threshold', e.target.value)} />
          <div className="field"><label htmlFor="agg">Item score aggregation</label><select id="agg" value={v.aggregation} onChange={(e) => set('aggregation', e.target.value)}><option value="mean">Mean of raters</option><option value="median">Median of raters</option></select></div>
          <TextInput label="Minimum companies to show ranking" type="number" min="3" value={v.min_companies_for_ranking} hint="Cannot go below 3 (anonymity)." onChange={(e) => set('min_companies_for_ranking', e.target.value)} />
        </div>
        <label className="row" style={{ marginBottom: 14 }}><input type="checkbox" checked={!!v.require_calibration} onChange={(e) => set('require_calibration', e.target.checked)} /> Lock real tasks until a rater has passed practice</label>
        <Button variant="primary" type="submit" disabled={save.isPending}>Save settings</Button>
      </form></Card>
    )}</Query>
  )
}

function Versioned({ kind, title, note }) {
  const q = useGet(`/admin/${kind}/`)
  const [body, setBody] = useState('')
  const [preview, setPreview] = useState(false)
  const pub = useAction(async () => (await api.post(`/admin/${kind}/`, { body })).data, { invalidate: [`/admin/${kind}/`], success: 'New version published.', onSuccess: () => setBody('') })
  return (
    <div className="stack">
      <Card title={`Publish new ${title.toLowerCase()} version (markdown)`}>
        <p className="muted small">{note}</p>
        {!body && q.data?.[0] && <Button size="sm" onClick={() => setBody(q.data[0].body)}>Start from current version</Button>}
        <div className="field"><label htmlFor="vb">Text</label><textarea id="vb" style={{ minHeight: 200 }} value={body} onChange={(e) => setBody(e.target.value)} /></div>
        {preview && <div className="card" dangerouslySetInnerHTML={{ __html: mdToHtml(body) }} />}
        <div className="row" style={{ marginTop: 8 }}><Button onClick={() => setPreview(!preview)}>{preview ? 'Hide preview' : 'Preview'}</Button><Button variant="primary" disabled={!body.trim() || pub.isPending} onClick={() => pub.mutate()}>Publish as v{(q.data?.[0]?.version || 0) + 1}</Button></div>
      </Card>
      <Card title="Versions"><Query q={q}>{(rows) => <Table empty="Nothing published." rows={rows.map((r) => ({ ...r, id: r.version }))} columns={[{ label: 'Version', render: (r) => `v${r.version}` }, { label: 'Published', render: (r) => fmtDate(r.published_at) }, { label: 'Excerpt', render: (r) => r.body.slice(0, 90) + '…' }]} />}</Query></Card>
    </div>
  )
}

function Templates() {
  const q = useGet('/admin/email-templates/')
  const { toast } = useToast()
  const [edit, setEdit] = useState(null)
  return (
    <Query q={q}>{(rows) => (
      <div className="stack">
        <p className="muted small">Placeholders use {'{name}'} syntax: {'{name} {company} {round} {language} {link} {deadline} {count} {submitted_at} {role}'} (availability depends on the email).</p>
        <Table rows={rows.map((r) => ({ ...r, id: r.key }))} columns={[{ label: 'Template', render: (r) => <strong>{r.key}</strong> }, { label: 'Subject', key: 'subject' }, { label: '', render: (r) => <Badge tone={r.customised ? 'info' : ''}>{r.customised ? 'customised' : 'default'}</Badge> }, { label: '', render: (r) => <Button size="sm" onClick={() => setEdit({ ...r })}>Edit</Button> }]} />
        {edit && <Modal wide title={`Edit: ${edit.key}`} onClose={() => setEdit(null)} actions={<>
          {edit.customised && <Button onClick={async () => { await api.delete(`/admin/email-templates/${edit.key}/`); toast('Reset to default.'); setEdit(null); q.refetch() }}>Reset to default</Button>}
          <Button onClick={() => setEdit(null)}>Cancel</Button>
          <Button variant="primary" onClick={async () => { try { await api.put(`/admin/email-templates/${edit.key}/`, { subject: edit.subject, body: edit.body }); toast('Saved.'); setEdit(null); q.refetch() } catch (e) { toast.error(e) } }}>Save</Button></>}>
          <TextInput label="Subject" value={edit.subject} onChange={(e) => setEdit({ ...edit, subject: e.target.value })} />
          <div className="field"><label htmlFor="eb">Body</label><textarea id="eb" style={{ minHeight: 200 }} value={edit.body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} /></div>
        </Modal>}
      </div>
    )}</Query>
  )
}

function EmailLog() {
  const q = useGet('/admin/notifications/')
  const [open, setOpen] = useState(null)
  return (
    <>
      <p className="muted small">Every email the system sends is logged here (in development it is also the place to find invite and secure links).</p>
      <Query q={q}>{(rows) => <Table empty="No emails yet." rows={rows} onRow={setOpen} columns={[{ label: 'When', render: (n) => fmtDate(n.created_at) }, { label: 'To', key: 'to' }, { label: 'Template', render: (n) => <Badge>{n.template}</Badge> }, { label: 'Subject', key: 'subject' }, { label: 'Status', render: (n) => <Badge tone={n.status === 'sent' ? 'ok' : 'bad'}>{n.status}</Badge> }]} />}</Query>
      {open && <Modal title={open.subject} onClose={() => setOpen(null)} actions={<Button onClick={() => setOpen(null)}>Close</Button>}><p className="muted small">To: {open.to}</p><pre className="md" style={{ wordBreak: 'break-all' }}>{open.body}</pre></Modal>}
    </>
  )
}
