// API からデータを読み込むフック(読み込み中・エラーの状態つき)
import { useCallback, useEffect, useState } from 'react'

export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    loader()
      .then((d) => alive && setData(d))
      .catch((err) => alive && setError(err instanceof Error ? err.message : String(err)))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])

  /** 表示中のまま最新の内容を読み直す */
  const reload = useCallback(() => setVersion((v) => v + 1), [])

  return { data, error, reload }
}
