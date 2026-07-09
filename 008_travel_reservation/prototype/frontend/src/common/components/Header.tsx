import { useEffect, useRef, useState } from 'react'
import './Header.css'

// ホーム画面・プラン詳細画面で共通して切り替える表示タブ。
// 'comingSoon'は未実装機能の枠として用意しているタブ。
export type Tab = 'plan' | 'comingSoon'

type HeaderProps = {
  userName: string
  activeTab: Tab
  onTabChange: (tab: Tab) => void
  onLogout: () => void
}

// 全画面共通で表示するヘッダー。ユーザー名表示・ログアウトメニュー・タブ切り替えを担当する。
function Header({ userName, activeTab, onTabChange, onLogout }: HeaderProps) {
  // ユーザー名クリックで開くログアウトメニューの開閉状態。
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)
  // メニュー外側のクリックを検知するために、メニュー領域のDOMを参照しておく。
  const userMenuRef = useRef<HTMLDivElement>(null)

  // メニューが開いている間、メニュー外側をクリックしたら自動的に閉じるための処理。
  // documentにイベントを登録し、クリック位置がメニュー内かどうかをcontainsで判定している。
  // クリーンアップ関数でイベント登録を解除しないと、アンマウント後もリスナーが残ってしまう。
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
    <header className="site-header">
      <div className="header-top">
        <div className="brand">AIS Travel</div>
        <div className="header-right" ref={userMenuRef}>
          <div className="header-user" onClick={() => setIsUserMenuOpen((open) => !open)}>
            こんにちは {userName} さん
          </div>
          {isUserMenuOpen && (
            <div className="user-menu">
              <span
                className="user-menu-item"
                onClick={() => {
                  // メニューを閉じてからログアウト処理を呼ぶ。
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
      </div>
      <div className="header-nav">
        {/* 現在選択中のタブに'active'クラスを付けて見た目を強調している */}
        <span
          className={`nav-tab${activeTab === 'plan' ? ' active' : ''}`}
          onClick={() => onTabChange('plan')}
        >
          宿泊プラン
        </span>
        <span
          className={`nav-tab${activeTab === 'comingSoon' ? ' active' : ''}`}
          onClick={() => onTabChange('comingSoon')}
        >
          Coming soon...
        </span>
      </div>
    </header>
  )
}

export default Header
