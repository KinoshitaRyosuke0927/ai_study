import { useState } from 'react'
import AdminLayout from './AdminLayout'
import { type AdminMenuItem } from './AdminSideMenu'
import './AdminHomeScreen.css'

type AdminHomeScreenProps = {
  userName: string
  onSwitchToTraveler: () => void
  onLogout: () => void
}

// 管理者向けホーム画面。サイドメニューの選択状態を管理し、AdminLayoutへ渡す。
// メインコンテンツ(ホーム/宿泊施設/予約状況それぞれの中身)は未実装のため、
// 現時点ではどの項目を選んでもプレースホルダーのみを表示する。
function AdminHomeScreen({ userName, onSwitchToTraveler, onLogout }: AdminHomeScreenProps) {
  const [selectedMenu, setSelectedMenu] = useState<AdminMenuItem>('home')

  return (
    <AdminLayout
      userName={userName}
      selectedMenu={selectedMenu}
      onSelectMenu={setSelectedMenu}
      onLogoClick={() => setSelectedMenu('home')}
      onSwitchToTraveler={onSwitchToTraveler}
      onLogout={onLogout}
    >
      <div className="admin-under-construction">Coming Soon...</div>
    </AdminLayout>
  )
}

export default AdminHomeScreen
