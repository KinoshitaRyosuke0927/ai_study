// 説明セル・問題文の Markdown 表示(表・数式・講座の画像に対応)
import 'katex/dist/katex.min.css'
import { createContext, useContext, type ReactNode } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'

/** 講座の画像の参照(![説明](image:ファイル名))を解決するための、表示中の講座の識別名 */
const CourseImagesContext = createContext<string | null>(null)

/** 子の Markdown で、講座の画像(image:ファイル名)を表示できるようにする */
export function CourseImagesProvider({ slug, children }: { slug: string; children: ReactNode }) {
  return <CourseImagesContext.Provider value={slug}>{children}</CourseImagesContext.Provider>
}

/** 講座の画像の表示用 URL */
export function courseImageUrl(slug: string, filename: string): string {
  return `/api/courses/${encodeURIComponent(slug)}/images/${encodeURIComponent(filename)}`
}

/** 見出しの文字列から、目次のリンク先に使う id を作る */
export function headingId(text: string): string {
  return `sec-${text.trim().replace(/\s+/g, '-')}`
}

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  return ''
}

// image: は講座の画像として残し、それ以外は既定の安全な URL の扱いにする
const urlTransform = (url: string) => (url.startsWith('image:') ? url : defaultUrlTransform(url))

// 1 行で書かれたディスプレイ数式 $$ ... $$(行にそれだけがあるもの)
const DISPLAY_MATH_LINE = /^[ \t]*\$\$(.+?)\$\$[ \t]*$/gm

/**
 * 1 行で書かれた $$ ... $$ を、$$ の行で囲んだブロックに書き換える。
 * remark-math は 1 行の $$ ... $$ を文中の数式として扱うため(分数や総和が小さく詰まって表示される)、
 * Jupyter と同じくディスプレイ数式として表示されるようにする。コードブロックの中は書き換えない。
 */
function normalizeDisplayMath(source: string): string {
  return source
    .split(/(^```[\s\S]*?^```)/m)
    .map((part) => (part.startsWith('```') ? part : part.replace(DISPLAY_MATH_LINE, (_, body: string) => `$$\n${body.trim()}\n$$`)))
    .join('')
}

/** inline: 表の項目名など、1行の短い文を段落にせずに表示する */
export function Markdown({ source, inline = false }: { source: string; inline?: boolean }) {
  const slug = useContext(CourseImagesContext)
  const Wrapper = inline ? 'span' : 'div'
  return (
    <Wrapper className={inline ? 'markdown markdown-inline' : 'markdown'}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        urlTransform={urlTransform}
        components={{
          h2: ({ children }) => <h2 id={headingId(textOf(children))}>{children}</h2>,
          // 1行表示では段落の余白を付けない
          ...(inline ? { p: ({ children }: { children?: ReactNode }) => <>{children}</> } : {}),
          // 外部リンクは別タブで開く
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          // 講座の画像(image:ファイル名)は、表示中の講座の画像の URL に置き換える
          img: ({ src, alt }) => {
            const name = typeof src === 'string' && src.startsWith('image:') ? src.slice('image:'.length) : null
            if (name !== null && !slug) return <span className="md-img-missing">[画像: {name}]</span>
            const url = name !== null && slug ? courseImageUrl(slug, name) : src
            return <img className="md-img" src={typeof url === 'string' ? url : undefined} alt={alt ?? ''} loading="lazy" />
          },
        }}
      >
        {normalizeDisplayMath(source)}
      </ReactMarkdown>
    </Wrapper>
  )
}
