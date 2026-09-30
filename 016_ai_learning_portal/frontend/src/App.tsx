// 画面のルーティング(未ログインならログイン画面を表示する)
import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { api, setDbStartingHandler } from './api/client'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Header } from './components/Header'
import { CatalogPage } from './pages/CatalogPage'
import { CourseDetailPage } from './pages/CourseDetailPage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { MyPage } from './pages/MyPage'
import { QuizPage } from './pages/QuizPage'
import { UnitPage } from './pages/UnitPage'
import { AdminCoursesPage } from './pages/admin/AdminCoursesPage'
import { AIJobPage } from './pages/admin/AIJobPage'
import { CourseCreatePage } from './pages/admin/CourseCreatePage'
import { CourseEditorPage } from './pages/admin/CourseEditorPage'
import { MembersProgressPage } from './pages/admin/MembersProgressPage'
import { PublishCheckPage } from './pages/admin/PublishCheckPage'
import { UsersPage } from './pages/admin/UsersPage'

function NotFound() {
  return (
    <>
      <Header />
      <main className="page">
        <h1 className="page-title">ページが見つかりません</h1>
        <Link to="/">ホームへ戻る</Link>
      </main>
    </>
  )
}

function AppRoutes() {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <LoginPage />
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/catalog" element={<CatalogPage />} />
      <Route path="/me" element={<MyPage />} />
      <Route path="/courses/:slug" element={<CourseDetailPage />} />
      <Route path="/courses/:slug/quiz" element={<QuizPage />} />
      <Route path="/units/:unitId" element={<UnitPage />} />
      {/* 管理者のみ(サーバ側でも権限を確認している) */}
      {user.is_admin && (
        <>
          <Route path="/admin" element={<AdminCoursesPage />} />
          <Route path="/admin/courses/new" element={<CourseCreatePage />} />
          <Route path="/admin/courses/:courseId" element={<CourseEditorPage />} />
          <Route path="/admin/courses/:courseId/publish" element={<PublishCheckPage />} />
          <Route path="/admin/ai-jobs/:jobId" element={<AIJobPage />} />
          <Route path="/admin/progress" element={<MembersProgressPage />} />
          <Route path="/admin/users" element={<UsersPage />} />
        </>
      )}
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

/** DB の起動待ち(停止中の DB を起動している間、定期的に接続を確かめ、つながったら再読み込みする) */
function DbStartingOverlay() {
  const [starting, setStarting] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    setDbStartingHandler(() => setStarting(true))
    return () => setDbStartingHandler(null)
  }, [])

  useEffect(() => {
    if (!starting) return
    const started = Date.now()
    const clock = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    const poll = window.setInterval(() => {
      api
        .health()
        .then(() => window.location.reload())
        .catch(() => undefined)
    }, 15000)
    return () => {
      window.clearInterval(clock)
      window.clearInterval(poll)
    }
  }, [starting])

  if (!starting) return null
  return (
    <div className="db-overlay" role="alertdialog" aria-live="polite" aria-label="データベースを起動しています">
      <div className="card db-overlay-card">
        <span className="runtime-badge runtime-running">
          <span className="runtime-dot" />
        </span>
        <h2>データベースを起動しています</h2>
        <p>しばらく使われていなかったため、データベースを停止していました。起動まで数分かかります。このままお待ちください(自動で再読み込みします)。</p>
        <div className="mono muted">
          {Math.floor(elapsed / 60)}分{String(elapsed % 60).padStart(2, '0')}秒 経過
        </div>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <DbStartingOverlay />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}
