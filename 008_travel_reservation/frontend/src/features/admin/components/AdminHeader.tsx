import { useEffect, useRef, useState } from 'react'
import './AdminHeader.css'

type AdminHeaderProps = {
  userName: string
  onLogoClick: () => void
  onSwitchToTraveler: () => void
  onLogout: () => void
}

// 管理者向け画面すべてで共通のヘッダー。ロゴ・管理者名・ログアウトメニューを表示する。
function AdminHeader({ userName, onLogoClick, onSwitchToTraveler, onLogout }: AdminHeaderProps) {
  // ユーザー名クリックで開くメニューの開閉状態。
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)
  // メニュー外側のクリックを検知するために、メニュー領域のDOMを参照しておく。
  const userMenuRef = useRef<HTMLDivElement>(null)

  // メニューが開いている間、メニュー外側をクリックしたら自動的に閉じるための処理。
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <header className="admin-header">
      <div className="admin-brand admin-brand-clickable" onClick={onLogoClick}>
        AIS Travel
      </div>
      <div className="admin-header-right" ref={userMenuRef}>
        <div className="admin-header-user" onClick={() => setIsUserMenuOpen((open) => !open)}>
          {userName} 様
        </div>
        {isUserMenuOpen && (
          <div className="admin-user-menu">
            <span
              className="admin-user-menu-item"
              onClick={() => {
                setIsUserMenuOpen(false)
                onSwitchToTraveler()
              }}
            >
              旅行者サイトに切替
            </span>
            <span
              className="admin-user-menu-item"
              onClick={() => {
                // 先にonLogoutで画面が切り替わるとこのDOMごと消えるため、開閉状態のリセットを先に行う。
                setIsUserMenuOpen(false)
                onLogout()
              }}
            >
              ログアウト
            </span>
          </div>
        )}
      </div>
    </header>
  )
}

export default AdminHeader
