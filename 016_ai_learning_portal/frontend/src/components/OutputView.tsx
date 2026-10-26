// セルの実行結果(標準出力・グラフ・作成したファイル・警告・エラー)の表示
import { useState } from 'react'
import type { RunResult } from '../python/protocol'
import { pythonRuntime } from '../python/runtime'

export function OutputView({ result, failure }: { result: RunResult | null; failure: string | null }) {
  if (failure) {
    return (
      <div className="cell-output">
        <pre className="output-error">{failure}</pre>
      </div>
    )
  }
  if (!result) return null
  const files = result.files ?? []
  const empty = !result.output && !result.stderr && !result.error && result.images.length === 0 && files.length === 0
  return (
    <div className="cell-output">
      {empty && <div className="output-empty">(出力はありません)</div>}
      {result.output && <pre className="output-text">{result.output}</pre>}
      {result.images.map((img, i) => (
        <img key={i} className="output-image" src={`data:image/png;base64,${img}`} alt={`グラフ ${i + 1}`} />
      ))}
      {files.length > 0 && <OutputFiles files={files} />}
      {result.stderr && <pre className="output-stderr">{result.stderr}</pre>}
      {result.error && <pre className="output-error">{result.error}</pre>}
    </div>
  )
}

/** セルで作成・更新したファイルの一覧とダウンロードボタン */
function OutputFiles({ files }: { files: RunResult['files'] }) {
  const [error, setError] = useState<string | null>(null)

  // ブラウザ内の Python からファイルを読み出して保存する
  const download = async (name: string) => {
    setError(null)
    try {
      const data = await pythonRuntime.readFile(name)
      const url = URL.createObjectURL(new Blob([data]))
      const a = document.createElement('a')
      a.href = url
      a.download = name
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="output-files">
      <div className="output-files-title">作成したファイル</div>
      {files.map((f) => (
        <div key={f.name} className="output-file">
          <span className="mono">{f.name}</span>
          <span className="muted small">{formatSize(f.size)}</span>
          <button type="button" className="btn btn-sm" onClick={() => void download(f.name)}>
            ダウンロード
          </button>
        </div>
      ))}
      {error && <div className="output-error small">{error}</div>}
    </div>
  )
}

/** ファイルサイズを読みやすい単位で表す */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
