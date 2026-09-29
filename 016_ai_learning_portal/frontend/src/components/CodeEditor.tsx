// コード入力欄(CodeMirror 6)。Shift+Enter で実行する
import { python } from '@codemirror/lang-python'
import { Prec } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import CodeMirror from '@uiw/react-codemirror'
import { useMemo } from 'react'

const theme = EditorView.theme({
  '&': { fontSize: '14px', backgroundColor: 'transparent' },
  '.cm-content': { fontFamily: "'IBM Plex Mono', ui-monospace, monospace", padding: '12px 0' },
  '.cm-gutters': { backgroundColor: 'transparent', border: 'none', color: '#8A8F96' },
  '.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'rgba(15, 107, 114, 0.05)' },
  '&.cm-focused': { outline: 'none' },
})

interface Props {
  value: string
  onChange: (value: string) => void
  onRun?: () => void
  ariaLabel: string
}

export function CodeEditor({ value, onChange, onRun, ariaLabel }: Props) {
  // Shift+Enter(Colab と同じ)でセルを実行する
  const extensions = useMemo(
    () => [
      python(),
      theme,
      EditorView.contentAttributes.of({ 'aria-label': ariaLabel }),
      Prec.highest(
        keymap.of([
          {
            key: 'Shift-Enter',
            run: () => {
              onRun?.()
              return true
            },
          },
        ]),
      ),
    ],
    [onRun, ariaLabel],
  )

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      extensions={extensions}
      basicSetup={{ foldGutter: false, highlightActiveLineGutter: true, autocompletion: true }}
    />
  )
}
