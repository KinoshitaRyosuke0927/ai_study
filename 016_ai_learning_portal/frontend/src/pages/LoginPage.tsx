// ログイン画面
import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const { login } = useAuth()
  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      await login(loginName, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={(e) => void onSubmit(e)}>
        <div className="brand brand-lg">
          <span className="brand-mark">AI</span>
          <span>AI学習ポータル</span>
        </div>
        <p className="muted">データサイエンスを、手を動かしながら学ぶ部署内の学習サービスです。</p>
        <label className="field">
          ログイン名
          <input value={loginName} onChange={(e) => setLoginName(e.target.value)} autoComplete="username" required autoFocus />
        </label>
        <label className="field">
          パスワード
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <button type="submit" className="btn btn-primary btn-block" disabled={sending}>
          {sending ? 'ログイン中…' : 'ログイン'}
        </button>
      </form>
    </main>
  )
}
