import './AdminSideMenu.css'

// 管理者向け画面すべてで共通のサイドメニュー項目。
export type AdminMenuItem = 'home' | 'facility' | 'reservation'

const MENU_LABELS: Record<AdminMenuItem, string> = {
  home: 'ホーム',
  facility: '宿泊施設',
  reservation: '予約状況',
}

const MENU_ITEMS: AdminMenuItem[] = ['home', 'facility', 'reservation']

type AdminSideMenuProps = {
  selectedMenu: AdminMenuItem
  onSelectMenu: (menu: AdminMenuItem) => void
}

// 管理者向け画面共通のサイドメニュー。選択中の項目に応じてメインコンテンツを切り替える想定。
function AdminSideMenu({ selectedMenu, onSelectMenu }: AdminSideMenuProps) {
  return (
    <nav className="admin-side-menu">
      {MENU_ITEMS.map((item) => (
        <span
          key={item}
          className={`admin-side-menu-item${selectedMenu === item ? ' active' : ''}`}
          onClick={() => onSelectMenu(item)}
        >
          {MENU_LABELS[item]}
        </span>
      ))}
    </nav>
  )
}

export default AdminSideMenu
