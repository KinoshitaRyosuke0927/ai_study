import { useState } from 'react'
import LoginScreen from './components/LoginScreen'
import HomeScreen from './components/HomeScreen'
import PlanDetailScreen from './components/PlanDetailScreen'
import type { Tab } from './components/Header'
import { searchPlan, type AccommodationPlan } from './api/searchPlanApi'

type Screen = 'login' | 'home' | 'planDetail'

function App() {
  const [screen, setScreen] = useState<Screen>('login')
  const [userName, setUserName] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('plan')
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)

  const [keyword, setKeyword] = useState('')
  const [plans, setPlans] = useState<AccommodationPlan[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const [hasSearched, setHasSearched] = useState(false)

  function handleLogout() {
    setScreen('login')
    setKeyword('')
    setPlans([])
    setErrorMessage('')
    setHasSearched(false)
  }

  function handleTabChange(tab: Tab) {
    setActiveTab(tab)
    setScreen('home')
  }

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

  if (screen === 'planDetail' && selectedPlanId !== null) {
    return (
      <PlanDetailScreen
        userName={userName}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onLogout={handleLogout}
        planId={selectedPlanId}
        onBack={() => setScreen('home')}
      />
    )
  }

  if (screen === 'home') {
    return (
      <HomeScreen
        userName={userName}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onLogout={handleLogout}
        onSelectPlan={(planId) => {
          setSelectedPlanId(planId)
          setScreen('planDetail')
        }}
        keyword={keyword}
        onKeywordChange={setKeyword}
        plans={plans}
        errorMessage={errorMessage}
        hasSearched={hasSearched}
        onSearch={handleSearch}
      />
    )
  }
  return (
    <LoginScreen
      onLogin={(name) => {
        setUserName(name)
        setScreen('home')
      }}
    />
  )
}

export default App
