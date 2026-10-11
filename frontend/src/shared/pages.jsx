import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { api, errMsg, fieldErrors } from './api'
import { HOME, useAuth } from './auth'
import { Button, Query, Spinner, TextInput, useToast } from './ui'
import { fmtDay, mdToHtml } from './util'

function AuthShell({ title, children, footer }) {
  return (
    <main className="auth-wrap">
      <div className="card auth-card">
        <div className="brand" style={{ padding: 0, marginBottom: 14 }}>EQAL<small>Interpreter quality rounds</small></div>
        <h1>{title}</h1>
        {children}
        <p className="small muted center" style={{ marginTop: 16 }}>{footer}<Link to="/privacy">Privacy</Link> · <Link to="/terms">Terms</Link></p>
      </div>
    </main>
  )
}

function downloadCodes(codes) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([`EQAL backup codes (each works once)\n\n${codes.join('\n')}\n`], { type: 'text/plain' }))
  a.download = 'eqal-backup-codes.txt'
  a.click()
}

export function Login() {
  const { user, setSession, ready } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [step, setStep] = useState('creds')           // creds | setup | code
  const [mfaToken, setMfaToken] = useState('')
  const [setup, setSetup] = useState(null)
  const [saved, setSaved] = useState(false)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (ready && user) return <Navigate to={HOME[user.role] || '/'} replace />

  const finish = (data) => { setSession(data); nav(loc.state?.from?.startsWith(`/${data.user.role}`) ? loc.state.from : HOME[data.user.role], { replace: true }) }
  const wrap = async (fn) => { setBusy(true); setError(''); try { await fn() } catch (e) { setError(errMsg(e)) } finally { setBusy(false) } }

  const submitCreds = (e) => { e.preventDefault(); wrap(async () => {
    const r = (await api.post('/auth/login/', form)).data
    if (!r.mfa_required) return finish(r)
    setMfaToken(r.mfa_token)
    if (r.mfa_setup_required) { setSetup((await api.post('/auth/mfa/setup/', { mfa_token: r.mfa_token })).data); setStep('setup') } else setStep('code')
  }) }
  const submitCode = (e) => { e.preventDefault(); wrap(async () => finish((await api.post('/auth/mfa/verify/', { mfa_token: mfaToken, code })).data)) }

  return (
    <AuthShell title={step === 'creds' ? 'Sign in' : step === 'setup' ? 'Set up two-factor authentication' : 'Two-factor code'}
      footer={step === 'creds' ? <><Link to="/forgot">Forgot password?</Link> · </> : null}>
      {error && <div className="alert bad" role="alert">{error}</div>}
      {step === 'creds' && (
        <form onSubmit={submitCreds}>
          <TextInput label="Email" type="email" autoComplete="username" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <TextInput label="Password" type="password" autoComplete="current-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <Button variant="primary" type="submit" disabled={busy} style={{ width: '100%', justifyContent: 'center' }}>{busy ? <Spinner /> : 'Sign in'}</Button>
          <p className="muted small" style={{ marginTop: 12 }}>Interpreters: use the personal link from your invitation email, or <Link to="/interpret/link">request a new link</Link>.</p>
        </form>
      )}
      {step === 'setup' && setup && (
        <form onSubmit={submitCode}>
          <p>Scan this QR code with an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password…).</p>
          <div className="center" style={{ background: '#fff', padding: 12, borderRadius: 10, width: 'fit-content', margin: '0 auto 10px' }}><QRCodeSVG value={setup.otpauth_uri} size={176} /></div>
          <p className="small muted center">Or enter this key manually: <span className="kbd">{setup.secret}</span></p>
          <div className="alert warn"><strong>Backup codes</strong> — store them safely, each works once:
            <div style={{ fontFamily: 'ui-monospace, monospace', columns: 2, margin: '8px 0' }}>{setup.backup_codes.map((c) => <div key={c}>{c}</div>)}</div>
            <Button size="sm" onClick={() => { downloadCodes(setup.backup_codes); setSaved(true) }}>Download codes</Button>
          </div>
          <TextInput label="6-digit code from the app" inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} />
          <Button variant="primary" type="submit" disabled={busy || !code} style={{ width: '100%', justifyContent: 'center' }}>Confirm and sign in</Button>
          {!saved && <p className="small muted">Please download your backup codes first.</p>}
        </form>
      )}
      {step === 'code' && (
        <form onSubmit={submitCode}>
          <p className="muted">Enter the 6-digit code from your authenticator app, or one of your backup codes.</p>
          <TextInput label="Code" inputMode="numeric" autoComplete="one-time-code" autoFocus required value={code} onChange={(e) => setCode(e.target.value)} />
          <Button variant="primary" type="submit" disabled={busy || !code} style={{ width: '100%', justifyContent: 'center' }}>Verify</Button>
        </form>
      )}
    </AuthShell>
  )
}

export function Forgot() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const submit = async (e) => { e.preventDefault(); await api.post('/auth/password-reset/', { email }); setSent(true) }
  return (
    <AuthShell title="Forgot password" footer={<><Link to="/login">Back to sign in</Link> · </>}>
      {sent ? <div className="alert ok">If that email has an account, a reset link is on its way.</div> : (
        <form onSubmit={submit}>
          <TextInput label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button variant="primary" type="submit">Send reset link</Button>
        </form>
      )}
    </AuthShell>
  )
}

function PasswordForm({ token, mode }) {
  const nav = useNavigate()
  const { toast } = useToast()
  const info = useQuery({ queryKey: ['invite', token], queryFn: async () => (await api.get(`/auth/invite/${token}/`)).data, retry: false })
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [terms, setTerms] = useState(false)
  const [errs, setErrs] = useState({}); const [msg, setMsg] = useState('')
  const submit = async (e) => {
    e.preventDefault(); setErrs({}); setMsg('')
    if (pw !== pw2) return setErrs({ password2: 'Passwords do not match.' })
    try {
      if (mode === 'invite') await api.post('/auth/invite/accept/', { token, password: pw, accept_terms: terms })
      else await api.post('/auth/password-reset/confirm/', { token, password: pw })
      toast(mode === 'invite' ? 'Account ready — please sign in.' : 'Password updated — please sign in.')
      nav('/login')
    } catch (er) { setErrs(fieldErrors(er)); setMsg(errMsg(er)) }
  }
  return (
    <AuthShell title={mode === 'invite' ? 'Welcome to EQAL' : 'Choose a new password'}>
      <Query q={info}>{(d) => (
        <form onSubmit={submit}>
          <p className="muted">{d.email} · {d.role}</p>
          {msg && <div className="alert bad" role="alert">{msg}</div>}
          <TextInput label="New password" type="password" autoComplete="new-password" required minLength={10} hint="At least 10 characters." error={errs.password} value={pw} onChange={(e) => setPw(e.target.value)} />
          <TextInput label="Repeat password" type="password" autoComplete="new-password" required error={errs.password2} value={pw2} onChange={(e) => setPw2(e.target.value)} />
          {mode === 'invite' && (
            <label className="row" style={{ marginBottom: 12, alignItems: 'flex-start' }}>
              <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} required />
              <span>I accept the <Link to="/terms" target="_blank">terms</Link> and have read the <Link to="/privacy" target="_blank">privacy notice</Link>.</span>
            </label>
          )}
          <Button variant="primary" type="submit">{mode === 'invite' ? 'Create account' : 'Update password'}</Button>
        </form>
      )}</Query>
    </AuthShell>
  )
}
export const InviteAccept = () => <PasswordForm token={useParams().token} mode="invite" />
export const ResetPassword = () => <PasswordForm token={useParams().token} mode="reset" />

function Doc({ kind, title }) {
  const q = useQuery({ queryKey: ['public', kind], queryFn: async () => (await api.get(`/public/${kind}/`)).data })
  return (
    <main className="auth-wrap">
      <div className="card" style={{ width: 'min(760px, 100%)' }}>
        <div className="row between"><div className="brand" style={{ padding: 0 }}>EQAL</div><Link to="/login">Sign in</Link></div>
        <h1>{title}</h1>
        <Query q={q}>{(d) => d.version ? (<><p className="muted small">Version {d.version} · published {fmtDay(d.published_at)}</p><div dangerouslySetInnerHTML={{ __html: mdToHtml(d.body) }} /></>) : <p className="muted">Not published yet.</p>}</Query>
        <p className="small muted"><Link to="/privacy">Privacy notice</Link> · <Link to="/terms">Terms</Link></p>
      </div>
    </main>
  )
}
export const Privacy = () => <Doc kind="privacy" title="Privacy notice" />
export const Terms = () => <Doc kind="terms" title="Terms of participation" />

export function ErrorPage({ code }) {
  const { user } = useAuth()
  return (
    <main className="auth-wrap">
      <div className="card auth-card center">
        <h1>{code === 403 ? 'Access denied' : 'Page not found'}</h1>
        <p className="muted">{code === 403 ? "You don't have permission to view this page." : "We couldn't find what you were looking for."}</p>
        <Link className="btn primary" to={user ? HOME[user.role] || '/' : '/login'}>Go home</Link>
      </div>
    </main>
  )
}

export function Home() {
  const { user, ready } = useAuth()
  if (!ready) return <div className="auth-wrap"><Spinner /></div>
  return <Navigate to={user ? HOME[user.role] : '/login'} replace />
}
