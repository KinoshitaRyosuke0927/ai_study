// 講座管理:下書きを含むすべての講座の一覧
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { LEVEL_LABEL } from '../../api/types'
import { AdminNav } from '../../components/admin/AdminNav'
import { formatDate } from '../../components/format'
import { Header } from '../../components/Header'
import { useLoad } from '../useLoad'

type Filter = 'all' | 'published' | 'draft'

export function AdminCoursesPage() {
  const { data: rows, error } = useLoad(() => api.admin.courses(), [])
  const [filter, setFilter] = useState<Filter>('all')
  const [keyword, setKeyword] = useState('')

  const visible = (rows ?? []).filter(
    (r) => (filter === 'all' || r.status === filter) && `${r.title} ${r.slug}`.toLowerCase().includes(keyword.trim().toLowerCase()),
  )

  return (
    <>
      <Header />
      <AdminNav />
      <main className="page">
        <div className="page-head">
          <h1 className="page-title">講座管理</h1>
          <Link className="btn btn-primary" to="/admin/courses/new">
            ＋ 新しい講座を作成
          </Link>
        </div>
        <div className="filter-row filters">
          {(
            [
              ['all', 'すべて'],
              ['published', '公開中'],
              ['draft', '下書き'],
            ] as [Filter, string][]
          ).map(([k, label]) => (
            <button key={k} type="button" className={`chip${filter === k ? ' chip-on' : ''}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>
              {label}
            </button>
          ))}
          <span className="spacer" />
          <label className="search">
            検索
            <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="講座名・識別名" />
          </label>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="card list-card">
          <table className="table">
            <thead>
              <tr>
                <th>講座名</th>
                <th>レベル</th>
                <th className="num">単元</th>
                <th>状態</th>
                <th className="num">検証</th>
                <th>作成者</th>
                <th className="num">受講者</th>
                <th className="num">修了者</th>
                <th>更新日</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/admin/courses/${r.id}`} className="strong-link">
                      {r.title}
                    </Link>
                    <div className="mono muted small">{r.slug}</div>
                  </td>
                  <td>
                    <span className="tag">{LEVEL_LABEL[r.level]}</span>
                  </td>
                  <td className="num mono">{r.unit_count}</td>
                  <td>
                    <span className={`tag ${r.status === 'draft' ? 'tag-draft' : 'tag-level'}`}>{r.status === 'draft' ? '下書き' : '公開中'}</span>
                  </td>
                  <td className={`num mono ${r.problem_count > 0 && r.verified_count === r.problem_count ? 'accent' : 'warm'}`}>
                    {r.verified_count} / {r.problem_count}
                  </td>
                  <td>{r.author_name ?? '—'}</td>
                  <td className="num mono">{r.learner_count}</td>
                  <td className="num mono">{r.completer_count}</td>
                  <td className="muted">{formatDate(r.updated_at)}</td>
                  <td className="row-links">
                    <Link to={`/admin/courses/${r.id}`}>編集</Link>
                    <Link to={`/admin/courses/${r.id}/publish`}>公開前チェック</Link>
                  </td>
                </tr>
              ))}
              {rows && visible.length === 0 && (
                <tr>
                  <td colSpan={10} className="muted">
                    該当する講座はありません。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="muted small">受講者は1単元以上完了した人数、修了者は小テストで満点を取った人数です。</p>
      </main>
    </>
  )
}
