// バックエンド API の呼び出し(同一オリジン・セッション Cookie で認証)
import type {
  AIJob,
  AIStatus,
  AdminCourseRow,
  CourseOutline,
  OutlineRequest,
  AdminUnit,
  AdminUser,
  CellIn,
  CourseEditor,
  CourseInfo,
  MemberDetail,
  Problem,
  ProblemIn,
  ProgressMatrix,
  PublishCheck,
  RunIn,
  UnitInfo,
  VerifyResult,
} from './adminTypes'
import type {
  AppConfig,
  CodeSubmit,
  CourseDetail,
  CourseSummary,
  Home,
  MyPage,
  Quiz,
  QuizAnswer,
  QuizResult,
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

/** DB が停止中で起動を待っている(503 db_starting)ときに呼ばれる処理(App が起動待ちの画面を出す) */
let onDbStarting: (() => void) | null = null
export function setDbStartingHandler(handler: (() => void) | null) {
  onDbStarting = handler
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  // FormData(ファイルのアップロード)はそのまま送り、それ以外は JSON にする
  const isForm = body instanceof FormData
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: body === undefined || isForm ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  if (!res.ok) {
    // FastAPI のエラーは {"detail": "..."} 形式
    let message = `エラーが発生しました(${res.status})`
    try {
      const data = await res.json()
      // DB の起動待ちは、画面全体で待機表示にする
      if (res.status === 503 && data.code === 'db_starting' && onDbStarting) onDbStarting()
      if (typeof data.detail === 'string') message = data.detail
      // 入力チェック(422)のエラーは項目ごとのメッセージをまとめる
      else if (Array.isArray(data.detail)) message = `入力内容を確認してください(${data.detail.map((d: { loc?: string[] }) => d.loc?.slice(-1)[0]).join(', ')})`
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
  health: () => request<{ status: string }>('GET', '/api/health'),
  config: () => request<AppConfig>('GET', '/api/config'),
  courses: () => request<CourseSummary[]>('GET', '/api/courses'),
  course: (slug: string) => request<CourseDetail>('GET', `/api/courses/${encodeURIComponent(slug)}`),
  unit: (id: number) => request<UnitDetail>('GET', `/api/units/${id}`),
  submitCode: (problemId: number, body: CodeSubmit) =>
    request<SubmitResult>('POST', `/api/problems/${problemId}/submit-code`, body),
  quiz: (slug: string) => request<Quiz>('GET', `/api/courses/${encodeURIComponent(slug)}/quiz`),
  submitQuiz: (slug: string, answers: QuizAnswer[]) =>
    request<QuizResult>('POST', `/api/courses/${encodeURIComponent(slug)}/quiz/attempts`, { answers }),
  home: () => request<Home>('GET', '/api/home'),
  myPage: () => request<MyPage>('GET', '/api/me/summary'),

  // ---------- 管理者 ----------
  admin: {
    courses: () => request<AdminCourseRow[]>('GET', '/api/admin/courses'),
    createCourse: (info: CourseInfo) => request<CourseEditor>('POST', '/api/admin/courses', info),
    editor: (id: number) => request<CourseEditor>('GET', `/api/admin/courses/${id}`),
    updateInfo: (id: number, info: CourseInfo) => request<CourseEditor>('PUT', `/api/admin/courses/${id}`, info),
    deleteCourse: (id: number) => request<void>('DELETE', `/api/admin/courses/${id}`),
    addUnit: (courseId: number, info: UnitInfo) => request<AdminUnit>('POST', `/api/admin/courses/${courseId}/units`, info),
    reorderUnits: (courseId: number, unitIds: number[]) =>
      request<void>('PUT', `/api/admin/courses/${courseId}/units/order`, { unit_ids: unitIds }),
    saveUnit: (unitId: number, body: UnitInfo & { cells: CellIn[] }) =>
      request<AdminUnit>('PUT', `/api/admin/units/${unitId}`, body),
    deleteUnit: (unitId: number) => request<void>('DELETE', `/api/admin/units/${unitId}`),
    saveQuiz: (courseId: number, questions: ProblemIn[]) =>
      request<Problem[]>('PUT', `/api/admin/courses/${courseId}/quiz`, { questions }),
    verify: (problemId: number, author: RunIn, ai: RunIn | null) =>
      request<VerifyResult>('POST', `/api/admin/problems/${problemId}/verify`, { author, ai }),
    acceptAuthor: (problemId: number, output: string) =>
      request<VerifyResult>('POST', `/api/admin/problems/${problemId}/accept-author`, { output }),
    publishCheck: (courseId: number) => request<PublishCheck>('GET', `/api/admin/courses/${courseId}/publish-check`),
    publish: (courseId: number, examplesOk: boolean) =>
      request<PublishCheck>('POST', `/api/admin/courses/${courseId}/publish`, { examples_ok: examplesOk }),
    unpublish: (courseId: number) => request<PublishCheck>('POST', `/api/admin/courses/${courseId}/unpublish`),
    uploadDataset: (courseId: number, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<CourseEditor>('POST', `/api/admin/courses/${courseId}/datasets`, form)
    },
    deleteDataset: (datasetId: number) => request<void>('DELETE', `/api/admin/datasets/${datasetId}`),
    progress: () => request<ProgressMatrix>('GET', '/api/admin/progress'),
    member: (userId: number) => request<MemberDetail>('GET', `/api/admin/members/${userId}`),
    users: () => request<AdminUser[]>('GET', '/api/admin/users'),
    addUser: (body: { login_name: string; display_name: string; password: string; is_admin: boolean }) =>
      request<AdminUser>('POST', '/api/admin/users', body),
    updateUser: (id: number, body: { display_name: string; is_admin: boolean; is_active: boolean; password?: string }) =>
      request<AdminUser>('PUT', `/api/admin/users/${id}`, body),
    deleteUser: (id: number) => request<void>('DELETE', `/api/admin/users/${id}`),
    confirm: (problemId: number) => request<VerifyResult>('POST', `/api/admin/problems/${problemId}/confirm`),
    importCourse: (file: File, replace: boolean) => {
      const form = new FormData()
      form.append('file', file)
      form.append('replace', String(replace))
      return request<CourseEditor>('POST', '/api/admin/import/course', form)
    },
    importUnit: (courseId: number, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<AdminUnit>('POST', `/api/admin/courses/${courseId}/import-unit`, form)
    },
    aiStatus: () => request<AIStatus>('GET', '/api/admin/ai/status'),
    aiOutline: (req: OutlineRequest) => request<CourseOutline>('POST', '/api/admin/ai/outline', req),
    aiCreateDraft: (slug: string, req: OutlineRequest, outline: CourseOutline) =>
      request<AIJob>('POST', '/api/admin/ai/drafts', { slug, request: req, outline }),
    aiJob: (jobId: number) => request<AIJob>('GET', `/api/admin/ai/jobs/${jobId}`),
    aiResumeJob: (jobId: number) => request<AIJob>('POST', `/api/admin/ai/jobs/${jobId}/resume`),
  },
}
