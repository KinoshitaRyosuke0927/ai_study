// 画面のルーティング(未ログインならログイン画面を表示する)
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Header } from './components/Header'
import { CourseDetailPage } from './pages/CourseDetailPage'
import { CourseListPage } from './pages/CourseListPage'
import { LoginPage } from './pages/LoginPage'
import { UnitPage } from './pages/UnitPage'

function NotFound() {
  return (
    <>
      <Header />
      <main className="page">
        <h1 className="page-title">ページが見つかりません</h1>
        <Link to="/">講座一覧へ戻る</Link>
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
      <Route path="/" element={<CourseListPage />} />
      <Route path="/courses/:slug" element={<CourseDetailPage />} />
      <Route path="/units/:unitId" element={<UnitPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}
