import { useEffect, useRef, useState } from 'react'
import { searchPlan, type AccommodationPlan } from '../api/searchPlanApi'
import './HomeScreen.css'

type HomeScreenProps = {
  userName: string
  onLogout: () => void
}

type Tab = 'plan' | 'comingSoon'

function HomeScreen({ userName, onLogout }: HomeScreenProps) {
  const [keyword, setKeyword] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('plan')
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)
  const [plans, setPlans] = useState<AccommodationPlan[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const [hasSearched, setHasSearched] = useState(false)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  async function handleSearch() {
    setErrorMessage('')
    const response = await searchPlan(keyword)
    if (response.messages.length > 0) {
      setErrorMessage(response.messages[0].message)
      setPlans([])
      setHasSearched(true)
      return
    }
    setPlans(response.plans)
    setHasSearched(true)
  }

  return (
    <div>
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
            onClick={() => setActiveTab('plan')}
          >
            宿泊プラン
          </span>
          <span
            className={`nav-tab${activeTab === 'comingSoon' ? ' active' : ''}`}
            onClick={() => setActiveTab('comingSoon')}
          >
            Coming soon...
          </span>
        </div>
      </header>
      <main className="home-body">
        {activeTab === 'plan' ? (
          <div className="search-box">
            <h3>キーワードから探す</h3>
            <div className="search-row">
              <input
                className="search-input"
                type="text"
                placeholder="ホテル名を入力"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
              <button className="search-btn" onClick={handleSearch}>
                検索
              </button>
            </div>
            {errorMessage && <div className="error-message">{errorMessage}</div>}
          </div>
        ) : null}
        {activeTab === 'plan' && hasSearched && (
          <div className="plan-list">
            {plans.length === 0 ? (
              <div className="plan-list-empty">該当する宿泊プランが見つかりませんでした。</div>
            ) : (
              plans.map((plan) => (
                <div className="plan-card" key={`${plan.hotel_id}-${plan.plan_id}`}>
                  <div className="plan-card-main">
                    <div className="plan-hotel-name">{plan.hotel_name}</div>
                    <div className="plan-name">{plan.plan_name}</div>
                  </div>
                  <div className="plan-price">{plan.price.toLocaleString()}円</div>
                </div>
              ))
            )}
          </div>
        )}
        {activeTab === 'comingSoon' && (
          <div className="under-construction">Coming soon...</div>
        )}
      </main>
    </div>
  )
}

export default HomeScreen
