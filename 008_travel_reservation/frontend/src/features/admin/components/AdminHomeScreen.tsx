import { useState } from 'react'
import AdminLayout from './AdminLayout'
import { type AdminMenuItem } from './AdminSideMenu'
import FacilityListScreen from '../facility/components/FacilityListScreen'
import FacilityDetailScreen from '../facility/components/FacilityDetailScreen'
import './AdminHomeScreen.css'

type AdminHomeScreenProps = {
  userId: number
  userName: string
  onSwitchToTraveler: () => void
  onLogout: () => void
}

// 管理者向けホーム画面。サイドメニューの選択状態を管理し、AdminLayoutへ渡す。
// 「宿泊施設」メニューでは、選択中の施設ID(selectedHotelId)の有無で一覧画面・詳細画面を切り替える。
// ホーム/予約状況は未実装のため、現時点ではプレースホルダーのみを表示する。
function AdminHomeScreen({ userId, userName, onSwitchToTraveler, onLogout }: AdminHomeScreenProps) {
  const [selectedMenu, setSelectedMenu] = useState<AdminMenuItem>('home')
  const [selectedHotelId, setSelectedHotelId] = useState<number | null>(null)

  // メニューを切り替えたら、以前選択していた施設の詳細画面には戻らないようリセットする。
  function handleSelectMenu(menu: AdminMenuItem) {
    setSelectedMenu(menu)
    setSelectedHotelId(null)
  }

  return (
    <AdminLayout
      userName={userName}
      selectedMenu={selectedMenu}
      onSelectMenu={handleSelectMenu}
      onLogoClick={() => handleSelectMenu('home')}
      onSwitchToTraveler={onSwitchToTraveler}
      onLogout={onLogout}
    >
      {selectedMenu === 'facility' &&
        (selectedHotelId === null ? (
          <FacilityListScreen ownerUserId={userId} onSelectHotel={setSelectedHotelId} />
        ) : (
          <FacilityDetailScreen hotelId={selectedHotelId} onBack={() => setSelectedHotelId(null)} />
        ))}
      {selectedMenu !== 'facility' && <div className="admin-under-construction">Coming Soon...</div>}
    </AdminLayout>
  )
}

export default AdminHomeScreen
