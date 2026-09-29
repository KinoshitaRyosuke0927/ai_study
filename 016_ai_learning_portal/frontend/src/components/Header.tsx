// 全画面共通のヘッダー
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Header({ breadcrumb }: { breadcrumb?: ReactNode }) {
  const { user, logout } = useAuth()
  const initials = (user?.display_name ?? '').replace(/\s/g, '').slice(0, 2)

  return (
    <header className="app-header">
      <Link to="/" className="brand">
        <span className="brand-mark">AI</span>
        <span>AI学習ポータル</span>
      </Link>
      {breadcrumb ? (
        <div className="breadcrumb">{breadcrumb}</div>
      ) : (
        <nav className="main-nav">
          <NavLink to="/" end>
            講座一覧
          </NavLink>
        </nav>
      )}
      {user && (
        <div className="user-menu">
          <span className="avatar" aria-hidden="true">
            {initials}
          </span>
          <span>{user.display_name}</span>
          {user.is_admin && <span className="badge badge-admin">管理者</span>}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void logout()}>
            ログアウト
          </button>
        </div>
      )}
    </header>
  )
}
