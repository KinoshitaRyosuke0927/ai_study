// 講座エディタ:講座情報・単元・小テスト・データファイルを編集する
import { useCallback, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { AdminUnit, CourseEditor, CourseInfo, Problem } from '../../api/adminTypes'
import { LEVEL_LABEL, type CourseLevel } from '../../api/types'
import { AdminNav } from '../../components/admin/AdminNav'
import { QuizEditor } from '../../components/admin/QuizEditor'
import { UnitEditor } from '../../components/admin/UnitEditor'
import { Header } from '../../components/Header'
import { useLoad } from '../useLoad'

/** 単元内の演習の検証済み数 */
function unitCounts(u: AdminUnit) {
  const problems = u.cells.flatMap((c) => (c.problem ? [c.problem] : []))
  return {
    done: problems.filter((p) => p.verify_status === 'verified').length,
    total: problems.length,
    mismatch: problems.some((p) => p.verify_status === 'mismatch'),
  }
}

const splitList = (s: string, sep: RegExp) => s.split(sep).map((x) => x.trim()).filter(Boolean)

/** 講座情報のフォーム */
function InfoForm({ editor, onSaved, onDeleted }: { editor: CourseEditor; onSaved: (e: CourseEditor) => void; onDeleted: () => void }) {
  const [slug, setSlug] = useState(editor.slug)
  const [title, setTitle] = useState(editor.title)
  const [level, setLevel] = useState<CourseLevel>(editor.level)
  const [summary, setSummary] = useState(editor.summary)
  const [tags, setTags] = useState(editor.tags.join(', '))
  const [outcomes, setOutcomes] = useState(editor.outcomes.join('\n'))
  const [libraries, setLibraries] = useState(editor.libraries.join(', '))
  const [prereqs, setPrereqs] = useState<number[]>(editor.prerequisite_ids)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    setMessage(null)
    const info: CourseInfo = {
      slug: slug.trim(),
      title,
      summary,
      level,
      tags: splitList(tags, /[,、]/),
      outcomes: splitList(outcomes, /\n/),
      libraries: splitList(libraries, /[,、]/),
      prerequisite_ids: prereqs,
    }
    try {
      onSaved(await api.admin.updateInfo(editor.id, info))
      setMessage({ ok: true, text: '保存しました' })
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!window.confirm(`講座「${editor.title}」を削除しますか?受講記録もすべて削除され、元に戻せません。`)) return
    try {
      await api.admin.deleteCourse(editor.id)
      onDeleted()
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  return (
    <div className="unit-editor">
      <h2 className="ue-title-static">講座情報</h2>
      <div className="card ue-info form-stack">
        <div className="ue-info-row">
          <label className="field spacer">
            講座タイトル
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="field field-mid">
            識別名(URL に使う英数字とハイフン)
            <input className="mono" value={slug} onChange={(e) => setSlug(e.target.value)} />
          </label>
          <label className="field field-narrow">
            レベル
            <select value={level} onChange={(e) => setLevel(e.target.value as CourseLevel)}>
              {(Object.keys(LEVEL_LABEL) as CourseLevel[]).map((l) => (
                <option key={l} value={l}>
                  {LEVEL_LABEL[l]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          概要
          <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </label>
        <div className="ue-info-row">
          <label className="field spacer">
            タグ(カンマ区切り)
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="統計, pandas" />
          </label>
          <label className="field spacer">
            使用ライブラリ(カンマ区切り)
            <input value={libraries} onChange={(e) => setLibraries(e.target.value)} placeholder="pandas, matplotlib" />
          </label>
        </div>
        <label className="field">
          この講座で身につくこと(1行に1つ)
          <textarea rows={3} value={outcomes} onChange={(e) => setOutcomes(e.target.value)} />
        </label>
        <fieldset className="check-list">
          <legend>前提となる講座</legend>
          {editor.other_courses.length === 0 && <span className="muted small">ほかの講座はまだありません</span>}
          {editor.other_courses.map((c) => (
            <label key={c.id}>
              <input
                type="checkbox"
                checked={prereqs.includes(c.id)}
                onChange={(e) => setPrereqs((p) => (e.target.checked ? [...p, c.id] : p.filter((x) => x !== c.id)))}
              />
              {c.title}
            </label>
          ))}
        </fieldset>
      </div>
      <div className="save-bar">
        <button type="button" className="btn btn-danger btn-sm" onClick={() => void remove()}>
          講座を削除
        </button>
        {message && <span className={message.ok ? 'accent' : 'warm'}>{message.text}</span>}
        <span className="spacer" />
        <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={saving}>
          {saving ? '保存中…' : '講座情報を保存'}
        </button>
      </div>
    </div>
  )
}

/** データファイルの管理 */
function DatasetsPanel({ editor, onChanged }: { editor: CourseEditor; onChanged: (e: CourseEditor) => void }) {
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const upload = async (file: File | undefined) => {
    if (!file) return
    setMessage(null)
    try {
      onChanged(await api.admin.uploadDataset(editor.id, file))
      setMessage({ ok: true, text: `${file.name} をアップロードしました` })
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      if (input.current) input.current.value = ''
    }
  }

  const remove = async (id: number, name: string) => {
    if (!window.confirm(`${name} を削除しますか?このファイルを読み込む例題・演習は動かなくなります。`)) return
    await api.admin.deleteDataset(id)
    onChanged(await api.admin.editor(editor.id))
  }

  return (
    <div className="unit-editor">
      <h2 className="ue-title-static">データファイル</h2>
      <p className="muted small">
        アップロードしたファイルは、受講者のブラウザの Python 実行環境に置かれ、<code>pd.read_csv("ファイル名")</code> で読み込めます(1ファイル 20MB まで。同じ名前は置き換え)。
      </p>
      <div className="card list-card">
        {editor.datasets.length === 0 && <div className="list-row muted">データファイルはありません。</div>}
        {editor.datasets.map((d) => (
          <div key={d.id} className="list-row">
            <span className="mono spacer">{d.filename}</span>
            <a href={d.url} download={d.filename}>
              ダウンロード
            </a>
            <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(d.id, d.filename)}>
              削除
            </button>
          </div>
        ))}
      </div>
      <div className="save-bar">
        {message && <span className={message.ok ? 'accent' : 'warm'}>{message.text}</span>}
        <span className="spacer" />
        <label className="btn btn-primary">
          ファイルをアップロード
          <input ref={input} type="file" className="sr-only" onChange={(e) => void upload(e.target.files?.[0])} />
        </label>
      </div>
    </div>
  )
}

export function CourseEditorPage() {
  const { courseId = '' } = useParams()
  const id = Number(courseId)
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { data, error } = useLoad(() => api.admin.editor(id), [id])
  const [override, setOverride] = useState<CourseEditor | null>(null)
  const [dirty, setDirty] = useState(false)

  // 画面上で更新した内容があればそちらを優先する(読み直すまで)
  const editor = override && override.id === id ? override : data
  const section = params.get('s') ?? 'info'

  const go = (s: string) => {
    if (dirty && !window.confirm('保存していない変更があります。移動すると変更は失われます。移動しますか?')) return
    setDirty(false)
    setParams({ s })
  }

  const refresh = useCallback(async () => {
    setOverride(await api.admin.editor(id))
  }, [id])

  if (error) {
    return (
      <>
        <Header />
        <AdminNav />
        <main className="page">
          <div className="form-error">{error}</div>
        </main>
      </>
    )
  }
  if (!editor) return <Header />

  const unit = section.startsWith('unit-') ? editor.units.find((u) => u.id === Number(section.slice(5))) : undefined
  const quizDone = editor.quiz.filter((p) => p.verify_status === 'verified').length

  const addUnit = async () => {
    if (dirty && !window.confirm('保存していない変更があります。単元を追加すると変更は失われます。続けますか?')) return
    const created = await api.admin.addUnit(editor.id, { title: `単元${editor.units.length + 1}`, summary: '', goals: [], estimated_minutes: 20 })
    await refresh()
    setDirty(false)
    setParams({ s: `unit-${created.id}` })
  }

  const importUnit = async (file: File | undefined) => {
    if (!file) return
    if (dirty && !window.confirm('保存していない変更があります。取り込むと変更は失われます。続けますか?')) return
    try {
      const unit = await api.admin.importUnit(editor.id, file)
      await refresh()
      setDirty(false)
      setParams({ s: `unit-${unit.id}` })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err))
    }
  }

  const moveUnit = async (u: AdminUnit, delta: -1 | 1) => {
    const ids = editor.units.map((x) => x.id)
    const i = ids.indexOf(u.id)
    ;[ids[i], ids[i + delta]] = [ids[i + delta], ids[i]]
    await api.admin.reorderUnits(editor.id, ids)
    await refresh()
  }

  const deleteUnit = async (u: AdminUnit) => {
    if (!window.confirm(`単元${u.position}「${u.title}」を削除しますか?単元の演習と受講者の提出記録も削除されます。`)) return
    await api.admin.deleteUnit(u.id)
    await refresh()
    setDirty(false)
    setParams({ s: 'info' })
  }

  return (
    <>
      <Header />
      <AdminNav />
      <div className="unit-layout editor-layout">
        <nav className="unit-toc" aria-label="講座の構成">
          <div className="editor-course">
            <div className="small muted">
              <Link to="/admin">講座管理</Link> /
            </div>
            <div className="editor-course-title">{editor.title}</div>
            <span className={`tag ${editor.status === 'draft' ? 'tag-draft' : 'tag-level'}`}>
              {editor.status === 'draft' ? '下書き' : '公開中'}
            </span>
          </div>
          <button type="button" className={`toc-item toc-btn${section === 'info' ? ' toc-current' : ''}`} onClick={() => go('info')}>
            講座情報
          </button>
          <div className="toc-label toc-label-gap">単元と検証状況</div>
          {editor.units.map((u) => {
            const c = unitCounts(u)
            return (
              <button
                key={u.id}
                type="button"
                className={`toc-item toc-btn${section === `unit-${u.id}` ? ' toc-current' : ''}`}
                onClick={() => go(`unit-${u.id}`)}
              >
                <span className="spacer">
                  {u.position}. {u.title}
                </span>
                {c.mismatch && <span className="vbadge vbadge-mismatch">要確認</span>}
                <span className={`mono small ${c.total > 0 && c.done === c.total ? 'accent' : 'muted'}`}>
                  {c.done}/{c.total}
                </span>
              </button>
            )
          })}
          <button type="button" className="toc-item toc-btn toc-add" onClick={() => void addUnit()}>
            ＋ 単元を追加
          </button>
          <label className="toc-item toc-btn toc-add">
            ＋ .ipynb から単元を追加
            <input
              type="file"
              accept=".ipynb"
              className="sr-only"
              onChange={(e) => {
                void importUnit(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </label>
          <button
            type="button"
            className={`toc-item toc-btn toc-quiz-open${section === 'quiz' ? ' toc-current' : ''}`}
            onClick={() => go('quiz')}
          >
            <span className="spacer">小テスト</span>
            <span className={`mono small ${editor.quiz.length > 0 && quizDone === editor.quiz.length ? 'accent' : 'muted'}`}>
              {quizDone}/{editor.quiz.length}
            </span>
          </button>
          <button type="button" className={`toc-item toc-btn${section === 'data' ? ' toc-current' : ''}`} onClick={() => go('data')}>
            データファイル({editor.datasets.length})
          </button>
          <div className="editor-note small">
            「検証」は、作成者が演習・小テストを自分で解き、その結果で正解を確定させることです。すべて検証済みになると公開できます。
          </div>
          <Link className="btn btn-dark btn-block" to={`/admin/courses/${editor.id}/publish`}>
            公開前チェックへ
          </Link>
        </nav>

        <main className="unit-main">
          <div className="unit-column editor-column">
            {section === 'info' && (
              <InfoForm
                key={`info-${editor.id}`}
                editor={editor}
                onSaved={setOverride}
                onDeleted={() => navigate('/admin')}
              />
            )}
            {unit && (
              <UnitEditor
                key={`unit-${unit.id}`}
                unit={unit}
                unitCount={editor.units.length}
                datasets={editor.datasets}
                onDirtyChange={setDirty}
                onSaved={(saved) => setOverride({ ...editor, units: editor.units.map((u) => (u.id === saved.id ? saved : u)) })}
                onMove={(delta) => void moveUnit(unit, delta)}
                onDelete={() => void deleteUnit(unit)}
                onVerified={() => void refresh()}
              />
            )}
            {section.startsWith('unit-') && !unit && <div className="muted">単元が見つかりません。左の一覧から選んでください。</div>}
            {section === 'quiz' && (
              <QuizEditor
                key={`quiz-${editor.id}`}
                courseId={editor.id}
                quiz={editor.quiz}
                units={editor.units}
                datasets={editor.datasets}
                onDirtyChange={setDirty}
                onSaved={(quiz: Problem[]) => setOverride({ ...editor, quiz })}
                onVerified={() => void refresh()}
              />
            )}
            {section === 'data' && <DatasetsPanel editor={editor} onChanged={setOverride} />}
          </div>
        </main>
      </div>
    </>
  )
}
