// セル1つ分の実行状態(実行中・結果・失敗)を扱うフック
import { useCallback, useState } from 'react'
import type { Dataset } from '../api/types'
import type { RunResult } from '../python/protocol'
import { pythonRuntime } from '../python/runtime'

export function useCellRunner(ctx: string, datasets: Dataset[]) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<RunResult | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  /** コードを実行して結果を表示する。実行できなかった場合は null を返す */
  const run = useCallback(
    async (code: string, test?: string): Promise<RunResult | null> => {
      setRunning(true)
      setFailure(null)
      try {
        const res = await pythonRuntime.run(ctx, code, datasets, test)
        setResult(res)
        return res
      } catch (err) {
        setResult(null)
        setFailure(err instanceof Error ? err.message : String(err))
        return null
      } finally {
        setRunning(false)
      }
    },
    [ctx, datasets],
  )

  const clear = useCallback(() => {
    setResult(null)
    setFailure(null)
  }, [])

  return { running, result, failure, run, clear }
}
