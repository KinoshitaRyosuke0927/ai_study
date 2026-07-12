import type { Tab } from '../components/Header'

// ヘッダー付き画面(HomeScreen・PlanDetailScreen)が共通して受け取る、
// ヘッダー表示・操作用のprops一式。
// 画面ごとにこの4つを個別に定義すると変更時に修正漏れが起きやすいため、型として共通化している。
export type HeaderNavProps = {
  userName: string
  activeTab: Tab | null
  onTabChange: (tab: Tab) => void
  onLogout: () => void
  onOpenMyPage: () => void
  onLogoClick: () => void
  // owner_flagを持つユーザ(施設管理者)かどうか。trueの場合のみ「管理者サイトに切替」メニューを表示する。
  isOwner: boolean
  onSwitchToAdmin: () => void
}
