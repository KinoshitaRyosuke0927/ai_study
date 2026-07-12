import { useState } from 'react'
import LoginScreen from './features/auth/components/LoginScreen'
import HomeScreen from './features/traveler/searchPlan/components/HomeScreen'
import PlanDetailScreen from './features/traveler/planDetail/components/PlanDetailScreen'
import MyPageScreen from './features/traveler/myPage/components/MyPageScreen'
import AdminHomeScreen from './features/admin/AdminHomeScreen'
import type { Tab } from './features/traveler/layout/components/Header'
import { searchPlan, type AccommodationPlan } from './features/traveler/searchPlan/api/searchPlanApi'

// このアプリはReact Routerなどのルーティングライブラリを使わず、
// 「今どの画面を表示しているか」をstateで管理する簡易的なSPA構成になっている。
type Screen = 'login' | 'home' | 'planDetail' | 'myPage' | 'adminHome'

function App() {
  // 画面遷移用のstate。ログイン→ホーム→プラン詳細という遷移をこのstateの切り替えで表現する。
  const [screen, setScreen] = useState<Screen>('login')
  const [userId, setUserId] = useState<number | null>(null)
  const [userName, setUserName] = useState('')
  // owner_flagを持つユーザ(施設管理者)としてログインしているかどうか。
  // trueの場合のみ旅行者向けヘッダーに「管理者サイトに切替」メニューを表示する。
  const [isOwner, setIsOwner] = useState(false)
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

  // ヘッダーのユーザーメニューから呼ばれる、管理者向けホーム画面への遷移処理。
  function handleSwitchToAdmin() {
    setScreen('adminHome')
  }

  // ヘッダー左上のロゴクリック時の処理。ログイン直後と同じ「宿泊プラン」タブのホーム画面に戻し、
  // 検索キーワード・検索結果などの状態もログイン直後の状態にリセットする。
  function handleLogoClick() {
    setActiveTab('plan')
    setScreen('home')
    setKeyword('')
    setPlans([])
    setErrorMessage('')
    setHasSearched(false)
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
        onLogoClick={handleLogoClick}
        isOwner={isOwner}
        onSwitchToAdmin={handleSwitchToAdmin}
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
        onLogoClick={handleLogoClick}
        isOwner={isOwner}
        onSwitchToAdmin={handleSwitchToAdmin}
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
        onLogoClick={handleLogoClick}
        isOwner={isOwner}
        onSwitchToAdmin={handleSwitchToAdmin}
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
  if (screen === 'adminHome' && userId !== null) {
    return (
      <AdminHomeScreen
        userId={userId}
        userName={userName}
        onSwitchToTraveler={handleLogoClick}
        onLogout={handleLogout}
      />
    )
  }

  // 上記いずれの条件にも当てはまらない場合(初期状態)はログイン画面を表示する。
  return (
    <LoginScreen
      onLogin={(id, name, isAdmin, isOwnerUser) => {
        setUserId(id)
        setUserName(name)
        setIsOwner(isOwnerUser)
        if (isAdmin) {
          // 管理者向けログインモードの場合は管理者向けホーム画面へ遷移する。
          setScreen('adminHome')
          return
        }
        // ログイン成功時はユーザーID・ユーザー名を保持し、必ず「宿泊プラン」タブのホーム画面から開始させる。
        setActiveTab('plan')
        setScreen('home')
      }}
    />
  )
}

export default App
