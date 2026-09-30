// 講座を作成:作成方法(AI で作成 / .ipynb を取り込む / 白紙から作成)を選んで下書きを作る
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { CourseOutline, OutlineRequest, OutlineUnit } from '../../api/adminTypes'
import { LEVEL_LABEL, type CourseLevel } from '../../api/types'
import { AdminNav } from '../../components/admin/AdminNav'
import { Header } from '../../components/Header'
import { useLoad } from '../useLoad'

type Method = 'ai' | 'ipynb' | 'blank'

const METHODS: { key: Method; label: string; desc: string }[] = [
  { key: 'ai', label: '題材から AI で作成', desc: '題材を入力すると AI が構成案を作ります。構成案を編集してから下書きを作ります' },
  { key: 'ipynb', label: '.ipynb を取り込む', desc: '講座フォルダ(course.json + .ipynb)を zip にして取り込みます' },
  { key: 'blank', label: '白紙から作成', desc: 'エディタで説明・例題・演習を一から書きます' },
]

const splitList = (s: string) => s.split(/[,、]/).map((x) => x.trim()).filter(Boolean)

/** 数値入力を範囲内に収める(空や数値でない場合は既定値) */
const clamp = (v: string, min: number, max: number, fallback: number) => {
  const n = Number(v)
  return Number.isFinite(n) && v !== '' ? Math.min(max, Math.max(min, Math.round(n))) : fallback
}

function LevelSelect({ value, onChange }: { value: CourseLevel; onChange: (v: CourseLevel) => void }) {
  return (
    <label className="field field-narrow">
      レベル
      <select value={value} onChange={(e) => onChange(e.target.value as CourseLevel)}>
        {(Object.keys(LEVEL_LABEL) as CourseLevel[]).map((l) => (
          <option key={l} value={l}>
            {LEVEL_LABEL[l]}
          </option>
        ))}
      </select>
    </label>
  )
}

function SlugField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="field">
      識別名(URL に使う英小文字・数字・ハイフン)
      <input
        className="mono"
        value={value}
        onChange={(e) => onChange(e.target.value.toLowerCase())}
        required
        pattern="[a-z0-9]+(-[a-z0-9]+)*"
        placeholder="例:time-series-basics"
      />
    </label>
  )
}

/** AI で作成:題材の入力 → 構成案の生成・編集 → 下書きの作成 */
function AICreate() {
  const navigate = useNavigate()
  const { data: status } = useLoad(() => api.admin.aiStatus(), [])
  const [req, setReq] = useState<OutlineRequest>({ title: '', topic: '', level: 'basic', unit_count: 5, libraries: ['pandas'], audience: '' })
  const [libraries, setLibraries] = useState('pandas')
  const [slug, setSlug] = useState('')
  const [outline, setOutline] = useState<CourseOutline | null>(null)
  const [busy, setBusy] = useState<'outline' | 'draft' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const genOutline = async (e?: FormEvent) => {
    e?.preventDefault()
    setBusy('outline')
    setError(null)
    try {
      const request = { ...req, libraries: splitList(libraries) }
      setReq(request)
      setOutline(await api.admin.aiOutline(request))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const createDraft = async () => {
    if (!outline) return
    setBusy('draft')
    setError(null)
    try {
      const job = await api.admin.aiCreateDraft(slug.trim(), req, outline)
      navigate(`/admin/ai-jobs/${job.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(null)
    }
  }

  const setUnit = (i: number, patch: Partial<OutlineUnit>) =>
    setOutline((o) => (o ? { ...o, units: o.units.map((u, x) => (x === i ? { ...u, ...patch } : u)) } : o))
  const moveUnit = (i: number, d: -1 | 1) =>
    setOutline((o) => {
      if (!o || i + d < 0 || i + d >= o.units.length) return o
      const units = [...o.units]
      ;[units[i], units[i + d]] = [units[i + d], units[i]]
      return { ...o, units }
    })

  if (status && !status.enabled) {
    return <div className="form-error">AI の接続情報が設定されていないため、AI で作成できません(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY)。</div>
  }

  return (
    <div className="ai-create">
      <form className="card create-form form-stack" onSubmit={(e) => void genOutline(e)}>
        <div className="ue-info-row">
          <label className="field spacer">
            講座タイトル(仮)
            <input value={req.title} onChange={(e) => setReq({ ...req, title: e.target.value })} required placeholder="例:時系列分析入門" />
          </label>
          <LevelSelect value={req.level} onChange={(level) => setReq({ ...req, level })} />
        </div>
        <label className="field">
          題材・扱いたい内容
          <textarea
            rows={4}
            value={req.topic}
            onChange={(e) => setReq({ ...req, topic: e.target.value })}
            required
            placeholder="例:日次の売上データを題材に、移動平均、トレンドと季節性の分解、自己相関と定常性、予測の評価までを扱いたい。"
          />
        </label>
        <div className="ue-info-row">
          <label className="field field-narrow">
            単元数の目安
            <input type="number" min={1} max={12} value={req.unit_count} onChange={(e) => setReq({ ...req, unit_count: clamp(e.target.value, 1, 12, 1) })} />
          </label>
          <label className="field spacer">
            使用ライブラリ(カンマ区切り)
            <input className="mono" value={libraries} onChange={(e) => setLibraries(e.target.value)} />
          </label>
        </div>
        <label className="field">
          対象者・前提知識(任意)
          <input value={req.audience} onChange={(e) => setReq({ ...req, audience: e.target.value })} placeholder="例:「統計の基礎」を修了した人" />
        </label>
        <div className="save-bar">
          <span className="spacer muted small">
            {status ? `構成案:${status.model_outline} ・ 下書き:${status.model_draft}` : ''}
          </span>
          <button type="submit" className="btn btn-primary" disabled={busy !== null}>
            {busy === 'outline' ? '構成案を作成中…(10秒ほど)' : outline ? '構成案を作り直す' : 'AI で構成案を作成'}
          </button>
        </div>
      </form>

      {error && <div className="form-error">{error}</div>}

      {outline && (
        <section className="card create-form form-stack outline">
          <div className="outline-head">
            <h2 className="ue-title-static">構成案</h2>
            <span className="vbadge vbadge-todo">AI 生成・未検証</span>
          </div>
          <p className="muted small">
            内容を確認・編集してから下書きを作成してください。下書きの演習・小テストはすべて「未検証」で作られ、作成者が解いて検証するまで公開できません。
          </p>
          <label className="field">
            講座タイトル
            <input value={outline.title} onChange={(e) => setOutline({ ...outline, title: e.target.value })} />
          </label>
          <label className="field">
            概要
            <textarea rows={3} value={outline.summary} onChange={(e) => setOutline({ ...outline, summary: e.target.value })} />
          </label>
          <div className="outline-units">
            {outline.units.map((u, i) => (
              <div key={i} className="outline-unit">
                <span className="mono accent outline-no">{i + 1}</span>
                <div className="spacer form-stack">
                  <input className="outline-title" aria-label={`単元${i + 1} のタイトル`} value={u.title} onChange={(e) => setUnit(i, { title: e.target.value })} />
                  <input aria-label={`単元${i + 1} の概要`} value={u.summary} onChange={(e) => setUnit(i, { summary: e.target.value })} />
                  <textarea
                    aria-label={`単元${i + 1} の学習目標`}
                    rows={2}
                    value={u.goals.join('\n')}
                    onChange={(e) => setUnit(i, { goals: e.target.value.split('\n') })}
                  />
                </div>
                <div className="outline-meta">
                  <label className="small">
                    演習
                    <input type="number" min={1} max={3} value={u.exercise_count} onChange={(e) => setUnit(i, { exercise_count: clamp(e.target.value, 1, 3, 1) })} />
                    問
                  </label>
                  <label className="small">
                    <input type="number" min={5} max={120} value={u.minutes} onChange={(e) => setUnit(i, { minutes: clamp(e.target.value, 5, 120, 20) })} />
                    分
                  </label>
                  <div className="row-actions">
                    <button type="button" className="icon-btn" aria-label="上へ" onClick={() => moveUnit(i, -1)} disabled={i === 0}>
                      ↑
                    </button>
                    <button type="button" className="icon-btn" aria-label="下へ" onClick={() => moveUnit(i, 1)} disabled={i === outline.units.length - 1}>
                      ↓
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="単元を削除"
                      onClick={() => setOutline({ ...outline, units: outline.units.filter((_, x) => x !== i) })}
                      disabled={outline.units.length <= 1}
                    >
                      ×
                    </button>
                  </div>
                </div>
              </div>
            ))}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setOutline({ ...outline, units: [...outline.units, { title: '新しい単元', summary: '', goals: [], minutes: 20, exercise_count: 1 }] })}
            >
              ＋ 単元を追加
            </button>
          </div>
          <label className="field field-inline">
            小テストの問題数
            <input type="number" min={3} max={20} value={outline.quiz_count} onChange={(e) => setOutline({ ...outline, quiz_count: clamp(e.target.value, 3, 20, 10) })} />
          </label>
          <SlugField value={slug} onChange={setSlug} />
          <div className="save-bar">
            <span className="spacer muted small">
              単元 {outline.units.length} ・ 演習 {outline.units.reduce((n, u) => n + u.exercise_count, 0)}問 ・ 小テスト {outline.quiz_count}問。作成には数分かかります。
            </span>
            <button type="button" className="btn btn-primary" onClick={() => void createDraft()} disabled={busy !== null || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)}>
              {busy === 'draft' ? '開始しています…' : 'この構成で下書きを作成'}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

/** .ipynb を取り込む:講座フォルダの zip をアップロード */
function IpynbImport() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [replace, setReplace] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const editor = await api.admin.importCourse(file, replace)
      navigate(`/admin/courses/${editor.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card create-form form-stack" onSubmit={(e) => void submit(e)}>
      <p className="small">
        講座フォルダ(<code>course.json</code>・単元の <code>.ipynb</code>・<code>quiz.ipynb</code>・<code>data/</code>)を zip にしてアップロードします。
        書き方は <code>docs/notebook-format.md</code> を参照してください。取り込んだ講座は下書きになります。
      </p>
      <label className="field">
        講座フォルダの zip
        <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
      </label>
      <label className="check-inline">
        <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
        同じ識別名の講座があれば置き換える(受講記録も削除されます)
      </label>
      {error && <div className="form-error">{error}</div>}
      <div className="save-bar">
        <span className="spacer muted small">既存の講座に単元を1つ追加する場合は、講座エディタの「.ipynb から単元を追加」を使います。</span>
        <button type="submit" className="btn btn-primary" disabled={busy || !file}>
          {busy ? '取り込み中…' : '取り込んでエディタへ'}
        </button>
      </div>
    </form>
  )
}

/** 白紙から作成 */
function BlankCreate() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [slug, setSlug] = useState('')
  const [level, setLevel] = useState<CourseLevel>('basic')
  const [summary, setSummary] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      const created = await api.admin.createCourse({
        slug: slug.trim(),
        title: title.trim(),
        summary,
        level,
        tags: [],
        outcomes: [],
        libraries: [],
        prerequisite_ids: [],
      })
      // 作成した講座の最初の単元をエディタで開く
      navigate(`/admin/courses/${created.id}?s=unit-${created.units[0]?.id ?? ''}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <form className="card create-form form-stack" onSubmit={(e) => void submit(e)}>
      <div className="ue-info-row">
        <label className="field spacer">
          講座タイトル
          <input value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="例:時系列分析入門" />
        </label>
        <LevelSelect value={level} onChange={setLevel} />
      </div>
      <SlugField value={slug} onChange={setSlug} />
      <label className="field">
        概要(あとから変更できます)
        <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
      </label>
      {error && <div className="form-error">{error}</div>}
      <div className="save-bar">
        <span className="spacer muted small">下書きとして作成され、公開前チェックを通るまで受講者には表示されません。</span>
        <button type="submit" className="btn btn-primary" disabled={sending}>
          {sending ? '作成中…' : '下書きを作成してエディタへ'}
        </button>
      </div>
    </form>
  )
}

export function CourseCreatePage() {
  const [method, setMethod] = useState<Method>('ai')
  return (
    <>
      <Header />
      <AdminNav />
      <main className="page create-page">
        <h1 className="page-title">新しい講座を作成</h1>
        <section className="form-stack">
          <div className="field-label">作成方法</div>
          <div className="method-grid">
            {METHODS.map((m) => (
              <button
                key={m.key}
                type="button"
                className={`method${method === m.key ? ' method-on' : ''}`}
                aria-pressed={method === m.key}
                onClick={() => setMethod(m.key)}
              >
                <span className="method-label">{m.label}</span>
                <span className="method-desc">{m.desc}</span>
              </button>
            ))}
          </div>
        </section>
        {method === 'ai' && <AICreate />}
        {method === 'ipynb' && <IpynbImport />}
        {method === 'blank' && <BlankCreate />}
      </main>
    </>
  )
}
