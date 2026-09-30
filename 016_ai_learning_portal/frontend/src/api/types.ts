// バックエンド(app/schemas.py)と対応する型定義

export interface User {
  id: number
  login_name: string
  display_name: string
  is_admin: boolean
}

export interface AppConfig {
  pyodide_base_url: string
}

export type CourseLevel = 'basic' | 'intermediate' | 'advanced'

export interface CourseSummary {
  slug: string
  title: string
  summary: string
  level: CourseLevel
  tags: string[]
  status: 'draft' | 'published'
  unit_count: number
  completed_unit_count: number
  exercise_count: number
  estimated_minutes: number
  next_unit_id: number | null
  completed: boolean
  quiz_question_count: number
  quiz_unlocked: boolean
  best_quiz_score: number | null
  published_at: string | null
}

export interface Prerequisite {
  slug: string
  title: string
  completed: boolean
}

export interface UnitSummary {
  id: number
  position: number
  title: string
  summary: string
  estimated_minutes: number
  exercise_count: number
  completed: boolean
}

export interface Dataset {
  id: number
  filename: string
  url: string
}

export interface CourseDetail extends CourseSummary {
  outcomes: string[]
  libraries: string[]
  author_name: string | null
  updated_at: string | null
  prerequisites: Prerequisite[]
  units: UnitSummary[]
  datasets: Dataset[]
}

export interface Exercise {
  problem_id: number
  title: string
  prompt: string
  hint: string
  starter_code: string
  grading: 'output' | 'test'
  test_code: string
  passed: boolean
  last_answer: string | null
}

export interface Cell {
  id: number
  cell_type: 'markdown' | 'code' | 'exercise'
  source: string
  exercise: Exercise | null
}

export interface UnitNav {
  id: number
  position: number
  title: string
  completed: boolean
}

export interface UnitDetail {
  id: number
  course_slug: string
  course_title: string
  position: number
  unit_count: number
  title: string
  goals: string[]
  estimated_minutes: number
  exercise_count: number
  completed: boolean
  cells: Cell[]
  units: UnitNav[]
  prev_unit: UnitNav | null
  next_unit: UnitNav | null
  datasets: Dataset[]
}

export interface CodeSubmit {
  code: string
  output: string
  error: string | null
  test_passed: boolean | null
}

export interface SubmitResult {
  passed: boolean
  message: string
  unit_completed: boolean
  unit_newly_completed: boolean
}

// ---------- 小テスト ----------
export interface RelatedUnit {
  id: number
  position: number
  title: string
}

export interface QuizQuestion {
  problem_id: number
  position: number
  answer_format: 'choice' | 'numeric' | 'code'
  prompt: string
  choices: string[]
  starter_code: string
  grading: 'output' | 'test'
  test_code: string
  related_unit: RelatedUnit | null
}

export interface QuizAttempt {
  id: number
  score: number
  total: number
  created_at: string
}

export interface Quiz {
  course_slug: string
  course_title: string
  unlocked: boolean
  remaining_units: RelatedUnit[]
  completed: boolean
  questions: QuizQuestion[]
  attempts: QuizAttempt[]
  datasets: Dataset[]
}

export interface QuizAnswer {
  problem_id: number
  answer: string
  output?: string
  error?: string | null
  test_passed?: boolean | null
}

export interface QuizQuestionResult {
  problem_id: number
  correct: boolean
  answered: boolean
  message: string
  explanation: string
  related_unit: RelatedUnit | null
}

export interface QuizResult {
  attempt: QuizAttempt
  perfect: boolean
  course_newly_completed: boolean
  results: QuizQuestionResult[]
}

// ---------- ホーム・マイページ ----------
export interface RoadmapCourse {
  slug: string
  title: string
  state: 'completed' | 'in_progress' | 'not_started'
}

export interface Home {
  continue_course: CourseSummary | null
  continue_unit_title: string | null
  in_progress: CourseSummary[]
  completed_course_count: number
  in_progress_count: number
  solved_exercise_count: number
  roadmap: Record<CourseLevel, RoadmapCourse[]>
  new_courses: CourseSummary[]
}

export interface MyPage {
  completed_course_count: number
  in_progress_count: number
  solved_exercise_count: number
  quiz_attempt_count: number
  in_progress: CourseSummary[]
  completed: { slug: string; title: string; completed_at: string; attempt_count: number }[]
  quiz_history: { course_slug: string; course_title: string; score: number; total: number; created_at: string }[]
  activities: { at: string; text: string }[]
}

export const LEVEL_LABEL: Record<CourseLevel, string> = {
  basic: '基礎',
  intermediate: '応用',
  advanced: '実践',
}
