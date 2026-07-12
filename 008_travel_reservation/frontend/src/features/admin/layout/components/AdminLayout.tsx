import type { ReactNode } from 'react'
import AdminHeader from './AdminHeader'
import AdminSideMenu, { type AdminMenuItem } from './AdminSideMenu'
import './AdminLayout.css'

type AdminLayoutProps = {
  userName: string
  selectedMenu: AdminMenuItem
  onSelectMenu: (menu: AdminMenuItem) => void
  onLogoClick: () => void
  onSwitchToTraveler: () => void
  onLogout: () => void
  children: ReactNode
}

// 管理者向け画面共通のレイアウト。ヘッダー・サイドメニュー・メインコンテンツの3要素で構成する。
// 各管理者向け画面はこのコンポーネントでchildrenを囲むことで、ヘッダー・サイドメニューを共通化できる。
function AdminLayout({
  userName,
  selectedMenu,
  onSelectMenu,
  onLogoClick,
  onSwitchToTraveler,
  onLogout,
  children,
}: AdminLayoutProps) {
  return (
    <div className="admin-shell">
      <AdminHeader
        userName={userName}
        onLogoClick={onLogoClick}
        onSwitchToTraveler={onSwitchToTraveler}
        onLogout={onLogout}
      />
      <div className="admin-body">
        {/* サイドメニューは普段は最小化しておき、この領域(左端の帯)にマウスが近づくとCSSのhoverでスライド表示される */}
        <div className="admin-side-menu-zone">
          <AdminSideMenu selectedMenu={selectedMenu} onSelectMenu={onSelectMenu} />
        </div>
        <main className="admin-content">{children}</main>
      </div>
    </div>
  )
}

export default AdminLayout
