// 講座を作成:作成方法(AI で作成 / 白紙から作成)を選んで下書きを作る
import { useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { CourseOutline, CourseType, OutlineRequest, OutlineUnit } from '../../api/adminTypes'
import { LEVEL_LABEL, type CourseLevel } from '../../api/types'
import { AdminNav } from '../../components/admin/AdminNav'
import { Header } from '../../components/Header'
import { useLoad } from '../useLoad'

type Method = 'ai' | 'blank'

const METHODS: { key: Method; label: string; desc: string }[] = [
  { key: 'ai', label: '題材から AI で作成', desc: '題材を入力すると AI が構成案を作ります。構成案を編集してから下書きを作ります' },
  { key: 'blank', label: '白紙から作成', desc: 'エディタで説明・例題・演習を一から書きます' },
]

// AI で作る講座のタイプ(タイプによって説明・演習の作り方が大きく変わる)
const COURSE_TYPES: { key: CourseType; label: string; desc: string }[] = [
  {
    key: 'concept',
    label: '概念理解型(コードなし)',
    desc: '概念の理解と手計算の力を身につける講座。図表と文章で説明し、演習は選択式・数値入力・表形式で出題します',
  },
  {
    key: 'practice',
    label: '実践型(コーディング中心)',
    desc: '実際のデータ分析の技術を身につける講座。例題コードを実行して結果を読み取り、コードを書く演習で学びます',
  },
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
  const [req, setReq] = useState<OutlineRequest>({
    title: '',
    course_type: 'practice',
    purpose: '',
    data_summary: '',
    topic: '',
    level: 'basic',
    unit_count: 5,
    libraries: ['pandas'],
    audience: '',
  })
  const [libraries, setLibraries] = useState('pandas')
  const [slug, setSlug] = useState('')
  const [outline, setOutline] = useState<CourseOutline | null>(null)
  const [busy, setBusy] = useState<'outline' | 'draft' | null>(null)
  const [error, setError] = useState<string | null>(null)
  // 講座のデータファイル(下書きの作成時に講座に登録する)と、その要約の作成状態
  const [files, setFiles] = useState<File[]>([])
  const [summarizing, setSummarizing] = useState(false)

  const summaryRequest = useRef(0)

  // データファイルが変わったら、要約(列・型・欠損・先頭の行)を作り直して依頼に含める
  const updateFiles = async (next: File[]) => {
    setFiles(next)
    setError(null)
    // 後から始めた要約だけを反映する(続けて選び直したときに古い要約で上書きしない)
    const requestId = ++summaryRequest.current
    if (next.length === 0) {
      setReq((r) => ({ ...r, data_summary: '' }))
      setSummarizing(false)
      return
    }
    setSummarizing(true)
    try {
      const { summary } = await api.admin.aiDataSummary(next)
      if (requestId === summaryRequest.current) setReq((r) => ({ ...r, data_summary: summary }))
    } catch (err) {
      if (requestId === summaryRequest.current) setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (requestId === summaryRequest.current) setSummarizing(false)
    }
  }

  // 選んだファイルを追加する(同じ名前のファイルは置き換え)
  const addFiles = (list: FileList | null) => {
    const chosen = Array.from(list ?? [])
    if (chosen.length === 0) return
    const names = new Set(chosen.map((f) => f.name))
    void updateFiles([...files.filter((f) => !names.has(f.name)), ...chosen])
  }

  // 登録したファイルを1つ取り除く
  const removeFile = (name: string) => void updateFiles(files.filter((f) => f.name !== name))

  const genOutline = async (e?: FormEvent) => {
    e?.preventDefault()
    setBusy('outline')
    setError(null)
    try {
      // 概念理解型はコードを書かないので、使用ライブラリは送らない
      const request = { ...req, libraries: req.course_type === 'concept' ? [] : splitList(libraries) }
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
      const job = await api.admin.aiCreateDraft(slug.trim(), req, outline, files)
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
        <div className="field-label">講座のタイプ</div>
        <div className="method-grid">
          {COURSE_TYPES.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`method${req.course_type === t.key ? ' method-on' : ''}`}
              aria-pressed={req.course_type === t.key}
              onClick={() => setReq({ ...req, course_type: t.key })}
            >
              <span className="method-label">{t.label}</span>
              <span className="method-desc">{t.desc}</span>
            </button>
          ))}
        </div>
        <div className="ue-info-row">
          <label className="field spacer">
            講座タイトル(仮)
            <input value={req.title} onChange={(e) => setReq({ ...req, title: e.target.value })} required placeholder="例:時系列分析入門" />
          </label>
          <LevelSelect value={req.level} onChange={(level) => setReq({ ...req, level })} />
        </div>
        <label className="field">
          講座の目的(受講後にできるようになってほしいこと)
          <textarea
            rows={2}
            value={req.purpose}
            onChange={(e) => setReq({ ...req, purpose: e.target.value })}
            required
            placeholder={
              req.course_type === 'concept'
                ? '例:統計検定2級の記述統計の範囲を理解し、試験形式の問題を手計算で解けるようになる。'
                : '例:売上データの時系列分析を、自分でコードを書いて一通り実施できるようになる。'
            }
          />
        </label>
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
          {req.course_type === 'practice' && (
            <label className="field spacer">
              使用ライブラリ(カンマ区切り)
              <input className="mono" value={libraries} onChange={(e) => setLibraries(e.target.value)} />
            </label>
          )}
        </div>
        <div className="field">
          データファイル(任意・CSV)
          <label className="file-drop">
            クリックして CSV ファイルを選択(複数可)
            <input
              type="file"
              className="sr-only"
              accept=".csv,text/csv"
              multiple
              onChange={(e) => {
                addFiles(e.target.files)
                // 同じファイルを取り除いた後に選び直せるよう、選択をリセットする
                e.target.value = ''
              }}
            />
          </label>
          {files.length > 0 && (
            <div className="card list-card">
              {files.map((f) => (
                <div key={f.name} className="list-row">
                  <span className="mono spacer">{f.name}</span>
                  <span className="muted small">{Math.max(1, Math.round(f.size / 1024))} KB</span>
                  <button type="button" className="btn btn-sm btn-danger" disabled={busy !== null} onClick={() => removeFile(f.name)}>
                    削除
                  </button>
                </div>
              ))}
            </div>
          )}
          <span className="muted small">
            講座で使うデータがあれば選んでください。AI がデータの列・型を読んでコードを書き、下書きの作成時に講座のデータファイルとして登録します。
          </span>
        </div>
        {summarizing && <div className="muted small">データファイルの内容を読み取っています…</div>}
        {req.data_summary && (
          <details className="data-summary">
            <summary className="small">AI に渡すデータの要約({files.length} ファイル)</summary>
            <pre className="mono small">{req.data_summary}</pre>
          </details>
        )}
        <label className="field">
          対象者・前提知識(任意)
          <input value={req.audience} onChange={(e) => setReq({ ...req, audience: e.target.value })} placeholder="例:「統計の基礎」を修了した人" />
        </label>
        <div className="save-bar">
          <span className="spacer muted small">
            {status
              ? `構成案:${status.model_outline} ・ 下書き:${status.model_draft} ・ コードの実行確認:${status.runner_enabled ? 'あり' : 'なし'}`
              : ''}
          </span>
          <button type="submit" className="btn btn-primary" disabled={busy !== null || summarizing}>
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
                    <input type="number" min={1} max={5} value={u.exercise_count} onChange={(e) => setUnit(i, { exercise_count: clamp(e.target.value, 1, 5, 3) })} />
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
              onClick={() => setOutline({ ...outline, units: [...outline.units, { title: '新しい単元', summary: '', goals: [], minutes: 30, exercise_count: 3 }] })}
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
              単元 {outline.units.length} ・ 演習 {outline.units.reduce((n, u) => n + u.exercise_count, 0)}問 ・ 小テスト {outline.quiz_count}問。作成には10〜20分ほどかかります(コードの実行確認を含む)。
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
        {method === 'blank' && <BlankCreate />}
      </main>
    </>
  )
}
