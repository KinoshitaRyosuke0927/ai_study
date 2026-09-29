// 例題コードセル(編集して実行できる。内容は保存しない)
import { useCallback, useState } from 'react'
import type { Dataset } from '../api/types'
import { pythonRuntime } from '../python/runtime'
import { CodeEditor } from './CodeEditor'
import { PlayIcon, StopIcon } from './Icons'
import { OutputView } from './OutputView'
import { useCellRunner } from './useCellRunner'

interface Props {
  ctx: string
  source: string
  datasets: Dataset[]
}

export function CodeCell({ ctx, source, datasets }: Props) {
  const [code, setCode] = useState(source)
  const { running, result, failure, run } = useCellRunner(ctx, datasets)
  const onRun = useCallback(() => void run(code), [run, code])

  return (
    <div className="nb-cell">
      <RunButton running={running} onRun={onRun} label="例題セルを実行" />
      <div className="cell-box">
        <div className="cell-editor cell-editor-example">
          <CodeEditor value={code} onChange={setCode} onRun={onRun} ariaLabel="例題コード" />
        </div>
        <OutputView result={result} failure={failure} />
      </div>
    </div>
  )
}

/** セル左の実行ボタン(実行中は停止ボタンになる) */
export function RunButton({
  running,
  onRun,
  label,
  primary = false,
}: {
  running: boolean
  onRun: () => void
  label: string
  primary?: boolean
}) {
  if (running) {
    return (
      <button type="button" className="run-btn run-btn-stop" onClick={() => pythonRuntime.stop()} aria-label="実行を停止">
        <StopIcon />
      </button>
    )
  }
  return (
    <button
      type="button"
      className={`run-btn${primary ? ' run-btn-primary' : ''}`}
      onClick={onRun}
      aria-label={label}
      title={`${label}(Shift+Enter)`}
    >
      <PlayIcon />
    </button>
  )
}
