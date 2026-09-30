// 管理画面のサブメニュー
import { NavLink } from 'react-router-dom'

export function AdminNav() {
  return (
    <nav className="admin-nav" aria-label="管理メニュー">
      <NavLink to="/admin" end>
        講座管理
      </NavLink>
      <NavLink to="/admin/courses/new">講座を作成</NavLink>
      <NavLink to="/admin/progress">メンバーの受講状況</NavLink>
      <NavLink to="/admin/users">メンバー管理</NavLink>
    </nav>
  )
}
