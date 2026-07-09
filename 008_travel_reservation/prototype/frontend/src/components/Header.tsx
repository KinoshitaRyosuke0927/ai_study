import { useEffect, useRef, useState } from 'react'
import './Header.css'

export type Tab = 'plan' | 'comingSoon'

type HeaderProps = {
  userName: string
  activeTab: Tab
  onTabChange: (tab: Tab) => void
  onLogout: () => void
}

function Header({ userName, activeTab, onTabChange, onLogout }: HeaderProps) {
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)

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
