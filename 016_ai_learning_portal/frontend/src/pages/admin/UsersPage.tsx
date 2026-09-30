// メンバー管理:メンバーの追加・表示名/権限/有効状態の変更・パスワードの再設定・削除
import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import type { AdminUser } from '../../api/adminTypes'
import { useAuth } from '../../auth/AuthContext'
import { AdminNav } from '../../components/admin/AdminNav'
import { formatDate } from '../../components/format'
import { Header } from '../../components/Header'
import { useLoad } from '../useLoad'

function UserRow({ user, isSelf, onChanged }: { user: AdminUser; isSelf: boolean; onChanged: () => void }) {
  const [name, setName] = useState(user.display_name)
  const [admin, setAdmin] = useState(user.is_admin)
  const [active, setActive] = useState(user.is_active)
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const changed = name !== user.display_name || admin !== user.is_admin || active !== user.is_active || password !== ''

  const save = async () => {
    setMessage(null)
    try {
      await api.admin.updateUser(user.id, { display_name: name, is_admin: admin, is_active: active, ...(password ? { password } : {}) })
      setPassword('')
      setMessage({ ok: true, text: password ? '保存しました(パスワードを変更)' : '保存しました' })
      onChanged()
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  const remove = async () => {
    if (!window.confirm(`${user.display_name}(${user.login_name})を削除しますか?受講記録もすべて削除されます。`)) return
    try {
      await api.admin.deleteUser(user.id)
      onChanged()
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  return (
    <tr>
      <td className="mono">{user.login_name}</td>
      <td>
        <input className="cell-input" aria-label={`${user.login_name} の表示名`} value={name} onChange={(e) => setName(e.target.value)} />
      </td>
      <td>
        <input type="checkbox" aria-label={`${user.login_name} を管理者にする`} checked={admin} disabled={isSelf} onChange={(e) => setAdmin(e.target.checked)} />
      </td>
      <td>
        <input type="checkbox" aria-label={`${user.login_name} を有効にする`} checked={active} disabled={isSelf} onChange={(e) => setActive(e.target.checked)} />
      </td>
      <td>
        <input
          className="cell-input"
          type="password"
          aria-label={`${user.login_name} の新しいパスワード`}
          placeholder="変更する場合のみ(8文字以上)"
          value={password}
          autoComplete="new-password"
          onChange={(e) => setPassword(e.target.value)}
        />
      </td>
      <td className="muted small">{formatDate(user.created_at)}</td>
      <td className="row-links">
        <button type="button" className="btn btn-sm btn-primary" onClick={() => void save()} disabled={!changed}>
          保存
        </button>
        {!isSelf && (
          <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove()}>
            削除
          </button>
        )}
        {message && <span className={`small ${message.ok ? 'accent' : 'warm'}`}>{message.text}</span>}
      </td>
    </tr>
  )
}

export function UsersPage() {
  const { user: me } = useAuth()
  const [version, setVersion] = useState(0)
  const { data: users, error } = useLoad(() => api.admin.users(), [version])
  const [loginName, setLoginName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  const add = async (e: FormEvent) => {
    e.preventDefault()
    setMessage(null)
    try {
      const created = await api.admin.addUser({ login_name: loginName.trim(), display_name: displayName.trim(), password, is_admin: isAdmin })
      setMessage({ ok: true, text: `${created.display_name}(${created.login_name})を追加しました。ログイン名とパスワードを本人に伝えてください。` })
      setLoginName('')
      setDisplayName('')
      setPassword('')
      setIsAdmin(false)
      setVersion((v) => v + 1)
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  return (
    <>
      <Header />
      <AdminNav />
      <main className="page">
        <h1 className="page-title">メンバー管理</h1>
        <form className="card create-form add-user" onSubmit={(e) => void add(e)}>
          <div className="field-label">メンバーを追加</div>
          <div className="ue-info-row">
            <label className="field field-mid">
              ログイン名(英数字と . _ -)
              <input className="mono" value={loginName} onChange={(e) => setLoginName(e.target.value)} required pattern="[A-Za-z0-9_.\-]+" />
            </label>
            <label className="field spacer">
              表示名
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </label>
            <label className="field field-mid">
              初期パスワード(8文字以上)
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" />
            </label>
            <label className="check-inline">
              <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
              管理者
            </label>
            <button type="submit" className="btn btn-primary">
              追加
            </button>
          </div>
          {message && <div className={message.ok ? 'verdict verdict-pass' : 'form-error'}>{message.text}</div>}
        </form>
        {error && <div className="form-error">{error}</div>}
        <div className="card list-card">
          <table className="table">
            <thead>
              <tr>
                <th>ログイン名</th>
                <th>表示名</th>
                <th>管理者</th>
                <th>有効</th>
                <th>パスワードの再設定</th>
                <th>登録日</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <UserRow key={`${u.id}-${version}`} user={u} isSelf={u.id === me?.id} onChanged={() => setVersion((v) => v + 1)} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">無効にしたメンバーはログインできなくなります(受講記録は残ります)。自分自身の管理者権限・有効状態は変更できません。</p>
      </main>
    </>
  )
}
