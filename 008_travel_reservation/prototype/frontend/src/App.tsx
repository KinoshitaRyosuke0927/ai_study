import { useState } from 'react'
import LoginScreen from './features/auth/components/LoginScreen'
import HomeScreen from './features/searchPlan/components/HomeScreen'
import PlanDetailScreen from './features/planDetail/components/PlanDetailScreen'
import MyPageScreen from './features/myPage/components/MyPageScreen'
import type { Tab } from './common/components/Header'
import { searchPlan, type AccommodationPlan } from './features/searchPlan/api/searchPlanApi'

// このアプリはReact Routerなどのルーティングライブラリを使わず、
// 「今どの画面を表示しているか」をstateで管理する簡易的なSPA構成になっている。
type Screen = 'login' | 'home' | 'planDetail' | 'myPage'

function App() {
  // 画面遷移用のstate。ログイン→ホーム→プラン詳細という遷移をこのstateの切り替えで表現する。
  const [screen, setScreen] = useState<Screen>('login')
  const [userId, setUserId] = useState<number | null>(null)
  const [userName, setUserName] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('plan')
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)

  // 検索キーワード・検索結果・エラーメッセージは、タブ切り替えや画面遷移をしても
  // 検索状態を保持したいため、各画面コンポーネント側ではなくAppに集約して管理している。
  const [keyword, setKeyword] = useState('')
  const [plans, setPlans] = useState<AccommodationPlan[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const [hasSearched, setHasSearched] = useState(false)

  // ログアウト時は認証情報だけでなく検索状態もリセットし、次に別ユーザーがログインしても
  // 前のユーザーの検索結果が残らないようにする。
  function handleLogout() {
    setScreen('login')
    setKeyword('')
    setPlans([])
    setErrorMessage('')
    setHasSearched(false)
  }

  // ヘッダーのタブ切り替えは、どの画面からでもホーム画面に戻す仕様のため、
  // タブの状態変更と同時にscreenも'home'に固定している。
  function handleTabChange(tab: Tab) {
    setActiveTab(tab)
    setScreen('home')
  }

  // ヘッダーのユーザーメニューから呼ばれる、マイページへの遷移処理。
  function handleOpenMyPage() {
    setScreen('myPage')
  }

  // 宿泊プラン検索APIを呼び出す処理。
  // バックエンドはエラー時も200 OKでmessagesにエラー内容を返す設計のため、
  // messagesが空かどうかで成功/失敗を判定している(HTTPステータスでは判定できない)。
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

  // 以下は画面のstateに応じて表示するコンポーネントを切り替える単純な条件分岐。
  // プラン詳細画面はselectedPlanIdが確定していないと表示できないため、両方の条件を確認する。
  if (screen === 'myPage' && userId !== null) {
    return (
      <MyPageScreen
        userName={userName}
        activeTab={null}
        onTabChange={handleTabChange}
        onLogout={handleLogout}
        onOpenMyPage={handleOpenMyPage}
        userId={userId}
      />
    )
  }

  if (screen === 'planDetail' && selectedPlanId !== null && userId !== null) {
    return (
      <PlanDetailScreen
        userName={userName}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onLogout={handleLogout}
        onOpenMyPage={handleOpenMyPage}
        userId={userId}
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
        onOpenMyPage={handleOpenMyPage}
        onSelectPlan={(planId) => {
          // 一覧でプランが選択されたら、そのIDを覚えつつ詳細画面へ遷移する。
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
  // 上記いずれの条件にも当てはまらない場合(初期状態)はログイン画面を表示する。
  return (
    <LoginScreen
      onLogin={(id, name) => {
        // ログイン成功時はユーザーID・ユーザー名を保持し、必ず「宿泊プラン」タブのホーム画面から開始させる。
        setUserId(id)
        setUserName(name)
        setActiveTab('plan')
        setScreen('home')
      }}
    />
  )
}

export default App
