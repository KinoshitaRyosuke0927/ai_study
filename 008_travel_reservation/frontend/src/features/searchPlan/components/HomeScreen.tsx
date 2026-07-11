import type { KeyboardEvent } from 'react'
import type { AccommodationPlan } from '../api/searchPlanApi'
import ScreenLayout from '../../../common/components/ScreenLayout'
import ErrorMessage from '../../../common/components/ErrorMessage'
import type { HeaderNavProps } from '../../../common/types/navigation'
import './HomeScreen.css'

type HomeScreenProps = HeaderNavProps & {
  onSelectPlan: (planId: number) => void
  keyword: string
  onKeywordChange: (keyword: string) => void
  plans: AccommodationPlan[]
  errorMessage: string
  // 検索を一度でも実行したかどうかのフラグ。
  // これがないと、初期表示時と「検索したが0件だった」時の見分けがつかず、
  // 検索前なのに「該当なし」と表示されてしまう。
  hasSearched: boolean
  onSearch: () => void
}

// ホーム画面。宿泊プランのキーワード検索フォームと検索結果一覧を表示する。
// 検索キーワードや結果などの状態は上位のAppコンポーネントで管理し、このコンポーネントは
// propsで受け取った値の表示とイベント通知(onSearch等)に専念する構成にしている。
function HomeScreen({
  onSelectPlan,
  keyword,
  onKeywordChange,
  plans,
  errorMessage,
  hasSearched,
  onSearch,
  ...headerProps
}: HomeScreenProps) {
  const { activeTab } = headerProps
  // キーワード未入力のときは検索ボタンを押せないようにするための判定。
  const canSearch = keyword.trim() !== ''

  // 検索欄でEnterキーを押したときも、ボタンクリックと同じ検索処理を実行できるようにする。
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && canSearch) {
      onSearch()
    }
  }

  return (
    <ScreenLayout {...headerProps}>
      {/* 「宿泊プラン」タブのときだけ検索フォームを表示する */}
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
          <ErrorMessage message={errorMessage} />
        </div>
      ) : null}
      {/* 検索を実行した後だけ結果一覧(0件メッセージ含む)を表示する */}
      {activeTab === 'plan' && hasSearched && (
        <div className="plan-list">
          {plans.length === 0 ? (
            <div className="plan-list-empty">該当する宿泊プランが見つかりませんでした。</div>
          ) : (
            plans.map((plan) => (
              // 同じホテルが複数プランを持つ可能性があるため、hotel_idとplan_idを組み合わせて一意なkeyにしている。
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
      {/* 未実装機能用のタブ。プレースホルダーとして固定メッセージのみ表示する */}
      {activeTab === 'comingSoon' && <div className="under-construction">Coming Soon...</div>}
    </ScreenLayout>
  )
}

export default HomeScreen
