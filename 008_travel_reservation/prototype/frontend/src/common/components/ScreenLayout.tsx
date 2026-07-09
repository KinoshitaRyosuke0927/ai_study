import type { ReactNode } from 'react'
import Header from './Header'
import type { HeaderNavProps } from '../types/navigation'
import './ScreenLayout.css'

// ヘッダー付きの画面(ホーム画面・プラン詳細画面)で共通する
// 「ヘッダー + スクロール可能なメインエリア」というレイアウトをまとめたコンポーネント。
// これを使うことで、各画面側はヘッダーのprops受け渡しやレイアウト用CSSを重複して書かずに済む。
type ScreenLayoutProps = HeaderNavProps & {
  children: ReactNode
}

function ScreenLayout({ children, ...headerProps }: ScreenLayoutProps) {
  return (
    <div className="screen-shell">
      {/* ヘッダー関連のprops(userName/activeTab/onTabChange/onLogout)はそのままHeaderへ渡す */}
      <Header {...headerProps} />
      <main className="home-body">{children}</main>
    </div>
  )
}

export default ScreenLayout
