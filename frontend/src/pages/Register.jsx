import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth, homeFor } from '../AuthContext.jsx'
import { COUNTIES } from '../constants.js'
import { ID_NUMBER_RE } from '../utils.js'
import { Notice } from '../components/ui.jsx'
import { resendSignupCode } from '../api.js'

export default function Register() {
  const { register, verifySignup } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [f, setF] = useState({ role: 'buyer', full_name: '', email: '', phone: '', password: '', county: '', business_name: '', id_number: '', address: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const dealer = f.role === 'dealer'

  const [step, setStep] = useState('form') 
  const [code, setCode] = useState('')
  const [info, setInfo] = useState('')
  const [wait, setWait] = useState(0) 

  useEffect(() => {
    if (wait <= 0) return
    const t = setTimeout(() => setWait(wait - 1), 1000)
    return () => clearTimeout(t)
  }, [wait])

  
  const submit = async (e) => {
    e.preventDefault()
    setError(''); setInfo('')
    if (f.password.length < 8) return setError('Password must be at least 8 characters.')
    if (dealer && !ID_NUMBER_RE.test(f.id_number.trim())) return setError('ID number looks wrong. It should be 7 or 8 digits.')
    setBusy(true)
    try {
      const r = await register({ ...f, id_number: f.id_number.trim() })
      setStep('code'); setWait(r.resend_after || 30)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  
  const verify = async (e) => {
    e.preventDefault()
    setError(''); setInfo('')
    if (!/^\d{6}$/.test(code)) return setError('Enter the 6-digit code.')
    setBusy(true)
    try {
      const u = await verifySignup(f.email, code)
      nav(loc.state?.from || homeFor(u), { replace: true })
    } catch (err) {
      setError(err.message); setBusy(false)
    }
  }

  const resend = async () => {
    setError(''); setInfo('')
    try {
      const r = await resendSignupCode(f.email)
      setWait(r.resend_after || 30); setCode(''); setInfo('We sent you a new code.')
    } catch (err) {
      setError(err.message)
    }
  }

  if (step === 'code') {
    return (
      <div className="auth-wrap">
        <form className="auth-card" onSubmit={verify}>
          <h1>Check your email</h1>
          <p className="muted">We sent a 6-digit code to <b>{f.email}</b>. It expires in 10 minutes.</p>
          {error && <Notice tone="error">{error}</Notice>}
          {info && <Notice>{info}</Notice>}
          <div className="field">
            <label htmlFor="otp">Verification code</label>
            <input id="otp" inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} placeholder="123456"
              required autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          </div>
          <button className="btn btn-primary btn-lg btn-block" disabled={busy}>{busy ? 'Verifying…' : 'Verify and create account'}</button>
          <p className="muted center">
            Didn't get it? <button type="button" className="link-btn" disabled={wait > 0} onClick={resend}>{wait > 0 ? `Resend code in ${wait}s` : 'Resend code'}</button>
            {' · '}<button type="button" className="link-btn" onClick={() => { setStep('form'); setCode(''); setError(''); setInfo('') }}>Change email</button>
          </p>
        </form>
      </div>
    )
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card wide" onSubmit={submit}>
        <h1>Create your account</h1>
        <p className="muted">Free for buyers. Dealers are verified before they can send offers.</p>

        <div className="seg" role="tablist" aria-label="Account type">
          <button type="button" role="tab" aria-selected={!dealer} className={!dealer ? 'on' : ''} onClick={() => setF({ ...f, role: 'buyer' })}>I'm buying a car</button>
          <button type="button" role="tab" aria-selected={dealer} className={dealer ? 'on' : ''} onClick={() => setF({ ...f, role: 'dealer' })}>I'm a dealer</button>
        </div>

        {error && <Notice tone="error">{error}</Notice>}

        <div className="form-grid">
          <div className="field">
            <label htmlFor="full_name">Full name</label>
            <input id="full_name" required value={f.full_name} onChange={set('full_name')} />
          </div>
          <div className="field">
            <label htmlFor="phone">Phone</label>
            <input id="phone" type="tel" placeholder="0712 345 678" pattern="\+?[0-9 \(\)\-]{7,20}" title="Digits, spaces, + ( ) - only (7 to 20 characters)" maxLength={20} required value={f.phone} onChange={set('phone')} />
          </div>
          <div className="field">
            <label htmlFor="r-email">Email</label>
            <input id="r-email" type="email" autoComplete="email" required value={f.email} onChange={set('email')} />
          </div>
          <div className="field">
            <label htmlFor="r-pass">Password</label>
            <input id="r-pass" type="password" autoComplete="new-password" minLength={8} maxLength={72} aria-describedby="pw-hint" required value={f.password} onChange={set('password')} />
            <span className="hint" id="pw-hint">8 to 72 characters</span>
          </div>
          <div className="field">
            <label htmlFor="r-county">County</label>
            <select id="r-county" required value={f.county} onChange={set('county')}>
              <option value="">Select county</option>
              {COUNTIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          {dealer && (
            <>
              <div className="field">
                <label htmlFor="biz">Business name</label>
                <input id="biz" required value={f.business_name} onChange={set('business_name')} />
              </div>
              <div className="field">
                <label htmlFor="idn">National ID number</label>
                <input id="idn" required inputMode="numeric" placeholder="12345678" pattern="\d{7,8}" title="7 or 8 digits" maxLength={8} value={f.id_number} onChange={(e) => setF({ ...f, id_number: e.target.value.replace(/\D/g, '') })} />
              </div>
              <div className="field">
                <label htmlFor="addr">Yard address</label>
                <input id="addr" value={f.address} onChange={set('address')} />
              </div>
            </>
          )}
        </div>

        {dealer && <Notice>After signing up, our team reviews your ID number. You can set up listings straight away, but can only send offers once approved.</Notice>}

        <button className="btn btn-primary btn-lg btn-block" disabled={busy}>{busy ? 'Sending code…' : 'Continue'}</button>
        <p className="muted center">Already registered? <Link to="/login" state={loc.state} className="link">Log in</Link></p>
      </form>
    </div>
  )
}
