interface ManualStep {
  step_number: number;
  title: string;
  action_type: string;
  target_element: string;
  description: string;
  expected_result: string;
  screenshot_filename: string;
}

interface ManualStructure {
  title: string;
  overview: string;
  target_application: string;
  prerequisites: string[];
  steps: ManualStep[];
}

interface GenerateResponse {
  status: string;
  manual_id: string;
  manual_html_url: string;
  manual_json: ManualStructure;
}

interface Props {
  manualData: GenerateResponse;
  onReset: () => void;
}

const ACTION_LABELS: Record<string, string> = {
  click: "クリック",
  input: "入力",
  scroll: "スクロール",
  navigate: "画面移動",
  other: "その他",
};

const ACTION_COLORS: Record<string, string> = {
  click: "bg-blue-100 text-blue-700",
  input: "bg-green-100 text-green-700",
  scroll: "bg-purple-100 text-purple-700",
  navigate: "bg-orange-100 text-orange-700",
  other: "bg-gray-100 text-gray-600",
};

export default function ManualViewer({ manualData, onReset }: Props) {
  const { manual_id, manual_json: manual } = manualData;

  const handleDownload = () => {
    window.open(`/api/manual/${manual_id}/download`, "_blank");
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-3xl mx-auto">

        {/* ヘッダーアクション */}
        <div className="flex items-center justify-between mb-6">
          <button
            onClick={onReset}
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            別の動画で試す
          </button>

          <button
            onClick={handleDownload}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            HTMLとしてダウンロード
          </button>
        </div>

        {/* マニュアルタイトル */}
        <div className="bg-blue-600 text-white rounded-2xl p-8 mb-6">
          <h1 className="text-2xl font-bold mb-3">{manual.title}</h1>
          <p className="text-blue-100 text-sm leading-relaxed">{manual.overview}</p>
        </div>

        {/* 情報カード */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">対象アプリケーション</p>
            <p className="font-semibold text-gray-800">{manual.target_application}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">前提条件</p>
            <ul className="space-y-1">
              {manual.prerequisites.map((prereq, i) => (
                <li key={i} className="text-sm text-gray-700 flex items-start gap-1.5">
                  <span className="text-blue-500 font-bold mt-0.5">✓</span>
                  {prereq}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* ステップ一覧 */}
        <h2 className="text-lg font-bold text-gray-900 mb-4 pb-2 border-b-2 border-blue-600">
          操作手順（全{manual.steps.length}ステップ）
        </h2>

        <div className="space-y-5">
          {manual.steps.map((step) => (
            <div key={step.step_number} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              {/* ステップヘッダー */}
              <div className="flex items-center gap-4 px-6 pt-5 pb-4">
                <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm flex-shrink-0">
                  {step.step_number}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-gray-900">{step.title}</span>
                  <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${ACTION_COLORS[step.action_type] || ACTION_COLORS.other}`}>
                    {ACTION_LABELS[step.action_type] || step.action_type}
                  </span>
                </div>
              </div>

              {/* ステップ内容 */}
              <div className="px-6 pb-5 space-y-3">
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">操作対象</p>
                  <p className="text-sm text-gray-600">{step.target_element}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">操作説明</p>
                  <p className="text-sm text-gray-800">{step.description}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">操作後の変化</p>
                  <div className="bg-blue-50 border-l-4 border-blue-500 rounded-r-lg px-4 py-2.5 text-sm text-blue-800">
                    {step.expected_result}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* フッター */}
        <div className="mt-10 text-center">
          <button
            onClick={onReset}
            className="inline-flex items-center gap-2 px-6 py-3 bg-gray-800 text-white font-medium rounded-xl hover:bg-gray-900 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            別の動画でマニュアルを作成する
          </button>
        </div>

      </div>
    </div>
  );
}
