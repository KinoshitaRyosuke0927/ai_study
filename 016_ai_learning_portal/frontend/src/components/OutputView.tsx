// セルの実行結果(標準出力・グラフ・警告・エラー)の表示
import type { RunResult } from '../python/protocol'

export function OutputView({ result, failure }: { result: RunResult | null; failure: string | null }) {
  if (failure) {
    return (
      <div className="cell-output">
        <pre className="output-error">{failure}</pre>
      </div>
    )
  }
  if (!result) return null
  const empty = !result.output && !result.stderr && !result.error && result.images.length === 0
  return (
    <div className="cell-output">
      {empty && <div className="output-empty">(出力はありません)</div>}
      {result.output && <pre className="output-text">{result.output}</pre>}
      {result.images.map((img, i) => (
        <img key={i} className="output-image" src={`data:image/png;base64,${img}`} alt={`グラフ ${i + 1}`} />
      ))}
      {result.stderr && <pre className="output-stderr">{result.stderr}</pre>}
      {result.error && <pre className="output-error">{result.error}</pre>}
    </div>
  )
}
