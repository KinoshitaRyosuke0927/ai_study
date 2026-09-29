// バックエンド API の呼び出し(同一オリジン・セッション Cookie で認証)
import type {
  AppConfig,
  CodeSubmit,
  CourseDetail,
  CourseSummary,
  SubmitResult,
  UnitDetail,
  User,
} from './types'

/** API がエラーを返したときの例外(status で 401 などを判別する) */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** 401 を受け取ったときに呼ばれる処理(ログイン画面へ戻すために AuthProvider が登録する) */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    // FastAPI のエラーは {"detail": "..."} 形式
    let message = `エラーが発生しました(${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // 本文が JSON でない場合は既定のメッセージを使う
    }
    if (res.status === 401 && path !== '/api/auth/login' && onUnauthorized) onUnauthorized()
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  login: (login_name: string, password: string) =>
    request<User>('POST', '/api/auth/login', { login_name, password }),
  logout: () => request<void>('POST', '/api/auth/logout'),
  me: () => request<User>('GET', '/api/auth/me'),
  config: () => request<AppConfig>('GET', '/api/config'),
  courses: () => request<CourseSummary[]>('GET', '/api/courses'),
  course: (slug: string) => request<CourseDetail>('GET', `/api/courses/${encodeURIComponent(slug)}`),
  unit: (id: number) => request<UnitDetail>('GET', `/api/units/${id}`),
  submitCode: (problemId: number, body: CodeSubmit) =>
    request<SubmitResult>('POST', `/api/problems/${problemId}/submit-code`, body),
}
