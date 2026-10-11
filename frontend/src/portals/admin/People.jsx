import { useState } from 'react'
import { api, fieldErrors } from '../../shared/api'
import { useAction, useGet } from '../../shared/hooks'
import { Badge, Button, Card, Modal, Query, StatusBadge, Table, TextInput, useToast } from '../../shared/ui'
import { fmtDate } from '../../shared/util'

function InviteNote({ link }) {
  if (!link) return null
  return <div className="alert warn small" style={{ wordBreak: 'break-all' }}>Dev mode — invite link: <a href={link}>{link}</a></div>
}

export function Companies() {
  const q = useGet('/admin/companies/')
  const { toast, confirm } = useToast()
  const [search, setSearch] = useState('')
  const [edit, setEdit] = useState(null)
  const [errs, setErrs] = useState({})
  const [link, setLink] = useState(null)

  const save = useAction(async (f) => {
    const body = { name: f.name, contact_email: f.contact_email, ...(f.id ? {} : { member_email: f.member_email }) }
    return (f.id ? await api.patch(`/admin/companies/${f.id}/`, body) : await api.post('/admin/companies/', body)).data
  }, { invalidate: ['/admin/companies/'], success: 'Saved.', onSuccess: (d) => { setEdit(null); setLink(d.invite_url || null) } })
  const resend = useAction(async (id) => (await api.post(`/admin/companies/${id}/resend-invite/`)).data, { success: 'Invite re-sent.', onSuccess: (d) => setLink(d.invite_url) })
  const toggle = useAction(async (c) => (await api.patch(`/admin/companies/${c.id}/`, { status: c.status === 'active' ? 'inactive' : 'active' })).data, { invalidate: ['/admin/companies/'] })

  const submit = async (e) => { e.preventDefault(); setErrs({}); try { await save.mutateAsync(edit) } catch (er) { setErrs(fieldErrors(er)) } }

  return (
    <div className="stack">
      <div className="page-head"><h1>Companies</h1><div className="row"><input style={{ width: 220 }} placeholder="Search…" aria-label="Search companies" value={search} onChange={(e) => setSearch(e.target.value)} /><Button variant="primary" onClick={() => { setErrs({}); setEdit({ name: '', contact_email: '', member_email: '' }) }}>+ Add company</Button></div></div>
      <InviteNote link={link} />
      <Query q={q}>{(rows) => (
        <Table empty="No companies yet." rows={rows.filter((c) => (c.name + c.contact_email).toLowerCase().includes(search.toLowerCase()))} columns={[
          { label: 'Company', render: (c) => <><strong>{c.name}</strong><div className="muted small">{c.contact_email}</div></> },
          { label: 'Login', render: (c) => <>{c.member_email || '—'} {c.member_mfa && <Badge tone="ok">2FA</Badge>}</> },
          { label: 'Interpreters', key: 'interpreters_count' },
          { label: 'Terms', render: (c) => c.terms_version_accepted ? <Badge tone={c.terms_current ? 'ok' : 'warn'}>v{c.terms_version_accepted}{c.terms_current ? '' : ' (outdated)'}</Badge> : <Badge tone="warn">not accepted</Badge> },
          { label: 'Status', render: (c) => <StatusBadge status={c.status} /> },
          { label: '', render: (c) => <div className="row"><Button size="sm" onClick={() => { setErrs({}); setEdit(c) }}>Edit</Button><Button size="sm" onClick={() => resend.mutate(c.id)}>Resend invite</Button>
            <Button size="sm" onClick={async () => { if (c.status === 'active' && !(await confirm({ message: `Deactivate ${c.name}? Their users will no longer be able to sign in.`, danger: true }))) return; toggle.mutate(c) }}>{c.status === 'active' ? 'Deactivate' : 'Activate'}</Button></div> },
        ]} />
      )}</Query>
      {edit && (
        <Modal title={edit.id ? 'Edit company' : 'Add company'} onClose={() => setEdit(null)}>
          <form onSubmit={submit}>
            <TextInput label="Company name" required value={edit.name} error={errs.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
            <TextInput label="Contact email" type="email" required value={edit.contact_email} error={errs.contact_email} onChange={(e) => setEdit({ ...edit, contact_email: e.target.value })} />
            {!edit.id && <TextInput label="Portal login email" type="email" hint="Receives the invite. Defaults to the contact email." value={edit.member_email} error={errs.member_email} onChange={(e) => setEdit({ ...edit, member_email: e.target.value })} />}
            <div className="actions" style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" type="submit" disabled={save.isPending}>{edit.id ? 'Save' : 'Create + send invite'}</Button></div>
          </form>
        </Modal>
      )}
    </div>
  )
}

export function Raters() {
  const q = useGet('/admin/raters/')
  const { confirm } = useToast()
  const [edit, setEdit] = useState(null)
  const [errs, setErrs] = useState({})
  const [link, setLink] = useState(null)
  const save = useAction(async (f) => {
    const body = { languages: f.languages, ...(f.id ? { is_calibrated: f.is_calibrated, active: f.active } : { email: f.email }) }
    return (f.id ? await api.patch(`/admin/raters/${f.id}/`, body) : await api.post('/admin/raters/', body)).data
  }, { invalidate: ['/admin/raters/'], success: 'Saved.', onSuccess: (d) => { setEdit(null); setLink(d.invite_url || null) } })
  const resend = useAction(async (id) => (await api.post(`/admin/raters/${id}/resend-invite/`)).data, { success: 'Invite re-sent.', onSuccess: (d) => setLink(d.invite_url) })
  const resetMfa = useAction(async (r) => api.post(`/admin/users/${r.user_id}/reset-mfa/`), { invalidate: ['/admin/raters/'], success: '2FA reset.' })
  const submit = async (e) => { e.preventDefault(); setErrs({}); try { await save.mutateAsync(edit) } catch (er) { setErrs(fieldErrors(er)) } }

  return (
    <div className="stack">
      <div className="page-head"><h1>Raters</h1><Button variant="primary" onClick={() => { setErrs({}); setEdit({ email: '', languages: '' }) }}>+ Add rater</Button></div>
      <InviteNote link={link} />
      <Query q={q}>{(rows) => (
        <Table empty="No raters yet." rows={rows} columns={[
          { label: 'Rater', key: 'email' },
          { label: 'Languages', render: (r) => r.languages.join(', ') || '—' },
          { label: '2FA', render: (r) => <Badge tone={r.mfa_enabled ? 'ok' : 'warn'}>{r.mfa_enabled ? 'on' : 'not set up'}</Badge> },
          { label: 'Calibrated', render: (r) => <Badge tone={r.is_calibrated ? 'ok' : 'warn'}>{r.is_calibrated ? 'yes' : `no (${r.practice_done} practice)`}</Badge> },
          { label: 'Workload', render: (r) => `${r.workload.done}/${r.workload.total}` },
          { label: 'Status', render: (r) => <StatusBadge status={r.active ? 'active' : 'inactive'} /> },
          { label: '', render: (r) => <div className="row"><Button size="sm" onClick={() => { setErrs({}); setEdit({ ...r, languages: r.languages.join(', ') }) }}>Edit</Button>
            <Button size="sm" onClick={() => resend.mutate(r.id)}>Resend invite</Button>
            <Button size="sm" onClick={async () => { if (await confirm({ message: `Reset 2FA for ${r.email}? They will set it up again at next login.`, danger: true })) resetMfa.mutate(r) }}>Reset 2FA</Button></div> },
        ]} />
      )}</Query>
      {edit && (
        <Modal title={edit.id ? 'Edit rater' : 'Add rater'} onClose={() => setEdit(null)}>
          <form onSubmit={submit}>
            {!edit.id && <TextInput label="Email" type="email" required value={edit.email} error={errs.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} />}
            <TextInput label="Languages" hint="Comma separated, e.g. Urdu, Punjabi" value={edit.languages} onChange={(e) => setEdit({ ...edit, languages: e.target.value })} />
            {edit.id && <>
              <label className="row"><input type="checkbox" checked={edit.is_calibrated} onChange={(e) => setEdit({ ...edit, is_calibrated: e.target.checked })} /> Calibrated (practice passed)</label>
              <label className="row" style={{ margin: '8px 0 12px' }}><input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} /> Active</label></>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" type="submit">Save</Button></div>
          </form>
        </Modal>
      )}
    </div>
  )
}
