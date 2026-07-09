import type { KeyboardEvent } from 'react'
import type { AccommodationPlan } from '../api/searchPlanApi'
import Header, { type Tab } from './Header'
import './HomeScreen.css'

type HomeScreenProps = {
  userName: string
  activeTab: Tab
  onTabChange: (tab: Tab) => void
  onLogout: () => void
  onSelectPlan: (planId: number) => void
  keyword: string
  onKeywordChange: (keyword: string) => void
  plans: AccommodationPlan[]
  errorMessage: string
  hasSearched: boolean
  onSearch: () => void
}

function HomeScreen({
  userName,
  activeTab,
  onTabChange,
  onLogout,
  onSelectPlan,
  keyword,
  onKeywordChange,
  plans,
  errorMessage,
  hasSearched,
  onSearch,
}: HomeScreenProps) {
  const canSearch = keyword.trim() !== ''

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && canSearch) {
      onSearch()
    }
  }

  return (
    <div className="screen-shell">
      <Header userName={userName} activeTab={activeTab} onTabChange={onTabChange} onLogout={onLogout} />
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
                onChange={(e) => onKeywordChange(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button className="search-btn" onClick={onSearch} disabled={!canSearch}>
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
                <div
                  className="plan-card"
                  key={`${plan.hotel_id}-${plan.plan_id}`}
                  onClick={() => onSelectPlan(plan.plan_id)}
                >
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
