import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { forgotPassword, resetPassword } from '../api.js'
import { Notice } from '../components/ui.jsx'

export default function ForgotPassword() {
  const nav = useNavigate()
  const loc = useLocation()
  const [step, setStep] = useState('email') 
  const [email, setEmail] = useState(loc.state?.email || '')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(0)

  useEffect(() => {
    if (wait <= 0) return
    const t = setTimeout(() => setWait(wait - 1), 1000)
    return () => clearTimeout(t)
  }, [wait])

  const sendCode = async (e) => {
    e?.preventDefault()
    setError(''); setInfo(''); setBusy(true)
    try {
      const r = await forgotPassword(email.trim())
      setStep('reset'); setWait(r.resend_after || 30)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const reset = async (e) => {
    e.preventDefault()
    setError(''); setInfo('')
    if (!/^\d{6}$/.test(code)) return setError('Enter the 6-digit code.')
    if (password.length < 8) return setError('Password must be at least 8 characters.')
    setBusy(true)
    try {
      await resetPassword(email.trim(), code, password)
      nav('/login', { replace: true, state: { notice: 'Password updated. Log in with your new password.' } })
    } catch (err) {
      setError(err.message); setBusy(false)
    }
  }

  if (step === 'reset') {
    return (
      <div className="auth-wrap">
        <form className="auth-card" onSubmit={reset}>
          <h1>Reset your password</h1>
          <p className="muted">If <b>{email}</b> has an account, we sent it a 6-digit code. It expires in 10 minutes.</p>
          {error && <Notice tone="error">{error}</Notice>}
          {info && <Notice>{info}</Notice>}
          <div className="field">
            <label htmlFor="rcode">Verification code</label>
            <input id="rcode" inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} placeholder="123456"
              required autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          </div>
          <div className="field">
            <label htmlFor="rpass">New password</label>
            <input id="rpass" type="password" autoComplete="new-password" minLength={8} maxLength={72} required value={password} onChange={(e) => setPassword(e.target.value)} />
            <span className="hint">8 to 72 characters</span>
          </div>
          <button className="btn btn-primary btn-lg btn-block" disabled={busy}>{busy ? 'Saving…' : 'Set new password'}</button>
          <p className="muted center">
            Didn't get it?{' '}
            <button type="button" className="link-btn" disabled={wait > 0 || busy} onClick={async () => { await sendCode(); setInfo('If that email has an account, we sent a new code.') }}>
              {wait > 0 ? `Resend code in ${wait}s` : 'Resend code'}
            </button>
          </p>
        </form>
      </div>
    )
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={sendCode}>
        <h1>Forgot your password?</h1>
        <p className="muted">Enter your email and we'll send you a code to choose a new one.</p>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="field">
          <label htmlFor="fp-email">Email</label>
          <input id="fp-email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-lg btn-block" disabled={busy}>{busy ? 'Sending…' : 'Send code'}</button>
        <p className="muted center"><Link to="/login" className="link">Back to log in</Link></p>
      </form>
    </div>
  )
}
