// 全画面共通のヘッダー
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Header({ breadcrumb }: { breadcrumb?: ReactNode }) {
  const { user, logout } = useAuth()

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
            ホーム
          </NavLink>
          <NavLink to="/catalog">講座カタログ</NavLink>
          <NavLink to="/me">マイ学習</NavLink>
          {user && (
            <NavLink to="/admin" className={({ isActive }) => `nav-admin${isActive ? ' active' : ''}`}>
              {user.is_admin ? '管理' : '講座管理'}
            </NavLink>
          )}
        </nav>
      )}
      {user && (
        <div className="user-menu">
          {/* 操作マニュアル(静的な HTML。別タブで開く) */}
          <a href="/manual/index.html" target="_blank" rel="noopener noreferrer" className="manual-link">
            マニュアル
          </a>
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
