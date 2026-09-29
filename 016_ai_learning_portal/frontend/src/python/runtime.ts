// Pyodide Worker を管理し、画面から Python を実行するためのランタイム(アプリ全体で1つ)
import { useSyncExternalStore } from 'react'
import { api } from '../api/client'
import type { Dataset } from '../api/types'
import type { RunResult, WorkerRequest, WorkerResponse } from './protocol'

export type RuntimeStatus = 'idle' | 'loading' | 'installing' | 'ready' | 'running' | 'failed'

/** 1回の実行の上限時間(パッケージの初回読み込みを含む) */
const RUN_TIMEOUT_MS = 120_000

/** 各メッセージ型から id を除いた型(union の各メンバーに分配する) */
type RequestBody = WorkerRequest extends infer R ? (R extends WorkerRequest ? Omit<R, 'id'> : never) : never

type Pending = { resolve: (res: WorkerResponse) => void; reject: (err: Error) => void }

class PythonRuntime {
  private worker: Worker | null = null
  private ready: Promise<void> | null = null
  private pending = new Map<number, Pending>()
  private nextId = 1
  private queue: Promise<unknown> = Promise.resolve()
  private writtenFiles = new Set<number>()
  private status: RuntimeStatus = 'idle'
  private listeners = new Set<() => void>()

  // ---------- 状態の購読(React から useRuntimeStatus で使う) ----------
  getStatus = () => this.status
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }
  private setStatus(status: RuntimeStatus) {
    this.status = status
    this.listeners.forEach((l) => l())
  }

  // ---------- Worker との通信 ----------
  private send(req: RequestBody, transfer: Transferable[] = []): Promise<WorkerResponse> {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.worker!.postMessage({ ...req, id }, transfer)
    })
  }

  private onMessage = (event: MessageEvent<WorkerResponse>) => {
    const msg = event.data
    if (msg.type === 'installing') {
      this.setStatus('installing')
      return
    }
    const p = this.pending.get(msg.id)
    if (!p) return
    this.pending.delete(msg.id)
    if (msg.type === 'fatal') p.reject(new Error(msg.message))
    else p.resolve(msg)
  }

  /** Worker を起動して Pyodide を読み込む(初回のみ。数秒〜十数秒かかる) */
  private ensureStarted(): Promise<void> {
    if (this.ready) return this.ready
    this.setStatus('loading')
    this.worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
    this.worker.onmessage = this.onMessage
    this.ready = (async () => {
      const config = await api.config()
      await this.send({ type: 'init', baseUrl: config.pyodide_base_url })
      this.setStatus('ready')
    })().catch((err) => {
      this.shutdown('failed')
      throw new Error(`Python 実行環境の読み込みに失敗しました: ${err instanceof Error ? err.message : err}`)
    })
    return this.ready
  }

  /** Worker を破棄する(停止・タイムアウト・読み込み失敗時) */
  private shutdown(status: RuntimeStatus, reason = '実行を停止しました') {
    this.worker?.terminate()
    this.worker = null
    this.ready = null
    this.writtenFiles.clear()
    this.pending.forEach((p) => p.reject(new Error(reason)))
    this.pending.clear()
    this.setStatus(status)
  }

  /** 前の実行が終わってから次を実行する(Python は1つずつしか動かせない) */
  private enqueue<T>(task: () => Promise<T>): Promise<T> {
    const next = this.queue.then(task, task)
    this.queue = next.catch(() => undefined)
    return next
  }

  // ---------- 公開メソッド ----------

  /** 講座のデータファイルを実行環境に配置する(配置済みのものは送らない) */
  private async writeDatasets(datasets: Dataset[]) {
    const missing = datasets.filter((d) => !this.writtenFiles.has(d.id))
    if (missing.length === 0) return
    const files = await Promise.all(
      missing.map(async (d) => {
        const res = await fetch(d.url, { credentials: 'same-origin' })
        if (!res.ok) throw new Error(`データファイル ${d.filename} を取得できませんでした`)
        return { name: d.filename, data: await res.arrayBuffer() }
      }),
    )
    await this.send({ type: 'files', files }, files.map((f) => f.data))
    missing.forEach((d) => this.writtenFiles.add(d.id))
  }

  /**
   * コードを実行する
   * @param ctx 実行コンテキスト(単元ごと。同じコンテキストのセルは変数を共有する)
   * @param test テストコード採点の問題のテストコード
   */
  run(ctx: string, code: string, datasets: Dataset[], test?: string): Promise<RunResult> {
    return this.enqueue(async () => {
      await this.ensureStarted()
      await this.writeDatasets(datasets)
      this.setStatus('running')
      const timer = setTimeout(
        () =>
          this.shutdown(
            'idle',
            `実行時間が上限(${RUN_TIMEOUT_MS / 1000} 秒)を超えたため停止しました。無限ループになっていないか確認してください。`,
          ),
        RUN_TIMEOUT_MS,
      )
      try {
        const res = await this.send({ type: 'run', ctx, code, test })
        if (res.type !== 'result') throw new Error('予期しない応答です')
        return res.result
      } catch (err) {
        // 停止・タイムアウトで Worker を破棄した場合もここに来る
        throw err instanceof Error ? err : new Error(String(err))
      } finally {
        clearTimeout(timer)
        if (this.worker) this.setStatus('ready')
      }
    })
  }

  /** 単元の変数をすべて消す(ランタイムの再起動に相当) */
  reset(ctx: string): Promise<void> {
    return this.enqueue(async () => {
      if (!this.worker) return
      await this.ensureStarted()
      await this.send({ type: 'reset', ctx })
    })
  }

  /** 実行中のコードを強制停止する(Worker を作り直すため、変数はすべて消える) */
  stop() {
    this.shutdown('idle')
  }
}

export const pythonRuntime = new PythonRuntime()

/** ランタイムの状態を React コンポーネントから参照する */
export function useRuntimeStatus(): RuntimeStatus {
  return useSyncExternalStore(pythonRuntime.subscribe, pythonRuntime.getStatus)
}
