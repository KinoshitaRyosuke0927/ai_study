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

export const LEVEL_LABEL: Record<CourseLevel, string> = {
  basic: '基礎',
  intermediate: '応用',
  advanced: '実践',
}
