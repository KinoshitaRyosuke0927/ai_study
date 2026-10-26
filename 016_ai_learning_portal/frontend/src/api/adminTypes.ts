// 管理者向け API(app/schemas_admin.py)と対応する型定義
import type { AnswerFormat, CourseLevel, Dataset, MyPage } from './types'

export type { AnswerFormat }
export type VerifyStatus = 'todo' | 'verified' | 'mismatch'

export interface AdminCourseRow {
  id: number
  slug: string
  title: string
  level: CourseLevel
  status: 'draft' | 'published'
  unit_count: number
  problem_count: number
  verified_count: number
  learner_count: number
  completer_count: number
  author_name: string | null
  updated_at: string | null
}

export interface CourseInfo {
  slug: string
  title: string
  summary: string
  level: CourseLevel
  tags: string[]
  outcomes: string[]
  libraries: string[]
  prerequisite_ids: number[]
}

export interface ProblemIn {
  id?: number | null
  answer_format: AnswerFormat
  title: string
  prompt: string
  hint: string
  starter_code: string
  grading: 'output' | 'test'
  test_code: string
  choices: string[] // 選択式の選択肢(表形式では列の選択肢)
  matrix_rows: string[] // 表形式の行
  correct_answer: string // 表形式は行ごとの正解を並べた JSON 配列の文字列
  tolerance: number
  explanation: string
  related_unit_id: number | null
  ai_model_answer: string
  author_answer: string
}

export interface Problem extends ProblemIn {
  id: number
  expected_output: string
  verify_status: VerifyStatus
  content_version: number
}

export interface CellIn {
  id?: number | null
  cell_type: 'markdown' | 'code' | 'exercise'
  source: string
  problem: ProblemIn | null
}

export interface AdminCell {
  id: number
  cell_type: 'markdown' | 'code' | 'exercise'
  source: string
  ai_generated: boolean
  problem: Problem | null
}

export interface UnitInfo {
  title: string
  summary: string
  goals: string[]
  estimated_minutes: number
}

export interface AdminUnit extends UnitInfo {
  id: number
  position: number
  cells: AdminCell[]
}

export interface CourseEditor extends CourseInfo {
  id: number
  status: 'draft' | 'published'
  units: AdminUnit[]
  quiz: Problem[]
  datasets: Dataset[]
  images: CourseImage[]
  other_courses: { id: number; title: string }[]
}

/** 講座の画像(Markdown から ![説明](image:ファイル名) で参照する) */
export interface CourseImage {
  id: number
  filename: string
  content_type: string
  size: number
  url: string
}

export interface RunIn {
  output: string
  error: string | null
  test_passed: boolean | null
}

export interface VerifyResult {
  verify_status: VerifyStatus
  message: string
  expected_output: string
  author_output: string
  ai_output: string | null
}

export interface CheckItem {
  label: string
  status: string
  unit_id: number | null
  problem_id: number | null
}

export interface Check {
  key: string
  label: string
  ok: boolean
  detail: string
  items: CheckItem[]
}

export interface PublishCheck {
  course_id: number
  slug: string
  title: string
  status: 'draft' | 'published'
  checks: Check[]
  publishable: boolean
}

export interface ProgressCell {
  course_id: number
  state: 'completed' | 'in_progress' | 'none'
  done: number
  total: number
}

export interface ProgressMatrix {
  courses: { id: number; slug: string; title: string; unit_count: number }[]
  members: {
    id: number
    login_name: string
    display_name: string
    is_admin: boolean
    last_activity: string | null
    cells: ProgressCell[]
  }[]
}

export interface AdminUser {
  id: number
  login_name: string
  display_name: string
  is_admin: boolean
  is_active: boolean
  created_at: string | null
}

export type MemberDetail = MyPage

export const VERIFY_LABEL: Record<VerifyStatus, string> = {
  todo: '未検証',
  verified: '検証済み',
  mismatch: '不一致',
}

/** 新しい問題の初期値 */
export function emptyProblem(format: AnswerFormat): ProblemIn {
  return {
    id: null,
    answer_format: format,
    title: '',
    prompt: '',
    hint: '',
    starter_code: '',
    grading: 'output',
    test_code: '',
    choices: format === 'choice' || format === 'matrix' ? ['', ''] : [],
    matrix_rows: format === 'matrix' ? [''] : [],
    correct_answer: format === 'matrix' ? '[""]' : '',
    tolerance: 1e-6,
    explanation: '',
    related_unit_id: null,
    ai_model_answer: '',
    author_answer: '',
  }
}

// ---------- AI による講座作成 ----------
export interface AIStatus {
  enabled: boolean
  model_outline: string
  model_draft: string
  runner_enabled: boolean // AI が作ったコードをサーバで実行して確かめられるか
}

/** AI で作る講座のタイプ(concept: 概念理解型・コードなし / practice: 実践型・コーディング中心) */
export type CourseType = 'concept' | 'practice'

export interface OutlineRequest {
  title: string
  course_type: CourseType
  purpose: string // 講座の目的
  data_summary: string // データファイルの要約(画面で選んだファイルからサーバが作る)
  topic: string
  level: CourseLevel
  unit_count: number
  libraries: string[]
  audience: string
}

export interface OutlineUnit {
  title: string
  summary: string
  goals: string[]
  minutes: number
  exercise_count: number
}

export interface CourseOutline {
  title: string
  summary: string
  tags: string[]
  outcomes: string[]
  libraries: string[]
  units: OutlineUnit[]
  quiz_count: number
}

export interface AIJob {
  id: number
  course_id: number | null
  status: 'queued' | 'running' | 'done' | 'failed'
  total_steps: number
  done_steps: number
  current_step: string
  message: string
}
