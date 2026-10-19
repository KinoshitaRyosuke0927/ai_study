// 管理画面のサブメニュー
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'

export function AdminNav() {
  const { user } = useAuth()
  return (
    <nav className="admin-nav" aria-label="管理メニュー">
      <NavLink to="/admin" end>
        講座管理
      </NavLink>
      <NavLink to="/admin/courses/new">講座を作成</NavLink>
      {/* メンバーの受講状況・メンバー管理は管理者だけ */}
      {user?.is_admin && <NavLink to="/admin/progress">メンバーの受講状況</NavLink>}
      {user?.is_admin && <NavLink to="/admin/users">メンバー管理</NavLink>}
    </nav>
  )
}
