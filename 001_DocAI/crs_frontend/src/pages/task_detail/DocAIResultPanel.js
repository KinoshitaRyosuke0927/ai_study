import { useEffect, useMemo, useState } from 'react';
import './taskDetail.css';

// ===== Markdown Parser =====
function parseMarkdown(md) {
  if (!md) return { imports: [], funcs: [] };
  const lines = md.split('\n');
  const result = { imports: [], funcs: [] };
  let section = null;
  let currentFunc = null;
  let currentSubsection = null;
  let purposeLines = [];

  const flushPurpose = () => {
    if (currentFunc && currentSubsection === 'purpose') {
      currentFunc.purpose = purposeLines.join(' ').trim();
      purposeLines = [];
    }
  };
  const pushFunc = () => {
    if (!currentFunc) return;
    flushPurpose();
    result.funcs.push(currentFunc);
    currentFunc = null;
    currentSubsection = null;
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '## 定数・インポート') { section = 'imports'; continue; }
    if (trimmed === '## 関数') { section = 'funcs'; continue; }
    if (trimmed === '---') { if (section === 'funcs') pushFunc(); continue; }

    if (section === 'imports') {
      const m = trimmed.match(/^-\s+\*\*(.+?)\*\*:\s*(.+)$/);
      if (m) result.imports.push({ name: m[1], desc: m[2] });
    } else if (section === 'funcs') {
      const h3 = trimmed.match(/^###\s+`(.+)`$/);
      if (h3) {
        pushFunc();
        currentFunc = { sig: h3[1], purpose: '', inputs: [], outputs: [], steps: [] };
        currentSubsection = null;
        continue;
      }
      if (!currentFunc) continue;
      if (trimmed === '#### 処理目的') { flushPurpose(); currentSubsection = 'purpose'; continue; }
      if (trimmed === '#### 入力') { flushPurpose(); currentSubsection = 'input'; continue; }
      if (trimmed === '#### 出力') { flushPurpose(); currentSubsection = 'output'; continue; }
      if (trimmed === '#### アルゴリズム') { flushPurpose(); currentSubsection = 'algorithm'; continue; }
      if (currentSubsection === 'purpose') {
        if (trimmed) purposeLines.push(trimmed);
      } else if (currentSubsection === 'input' || currentSubsection === 'output') {
        const m = trimmed.match(/^-\s+`(.+?)`:\s*(.+)$/);
        if (m) {
          const arr = currentSubsection === 'input' ? currentFunc.inputs : currentFunc.outputs;
          arr.push({ name: m[1], desc: m[2] });
        }
      } else if (currentSubsection === 'algorithm') {
        const numbered = trimmed.match(/^(\d+)\.\s+(.+)$/);
        if (numbered) {
          currentFunc.steps.push(numbered[2]);
        } else {
          const sub = trimmed.match(/^-\s+(.+)$/);
          if (sub && currentFunc.steps.length > 0) {
            const last = currentFunc.steps.length - 1;
            currentFunc.steps[last] = currentFunc.steps[last] + '\n- ' + sub[1];
          }
        }
      }
    }
  }
  if (section === 'funcs') pushFunc();
  return result;
}

// Split params handling nested brackets like list[File], dict[int, str]
function splitParams(params) {
  const parts = [];
  let depth = 0;
  let current = '';
  for (const ch of params) {
    if (ch === '[') depth++;
    else if (ch === ']') depth--;
    if (ch === ',' && depth === 0) { parts.push(current.trim()); current = ''; }
    else current += ch;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

// Inline rendering: `code` and **bold**
function renderInline(text) {
  if (!text) return null;
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="docai-bold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="docai-inline-code">{part.slice(1, -1)}</code>;
    }
    return part || null;
  });
}

// Render a step text that may contain sub-bullet lines ("- text")
function renderStepText(text) {
  const lines = text.split('\n');
  const result = [];
  let bullets = [];

  const flushBullets = () => {
    if (bullets.length === 0) return;
    result.push(
      <ul key={`ul-${result.length}`} className="docai-step-sublist">
        {bullets.map((b, j) => <li key={j}>{renderInline(b)}</li>)}
      </ul>
    );
    bullets = [];
  };

  for (const line of lines) {
    const sub = line.match(/^-\s+(.+)$/);
    if (sub) {
      bullets.push(sub[1]);
    } else {
      flushBullets();
      if (line.trim()) {
        result.push(<span key={`t-${result.length}`}>{renderInline(line)}</span>);
      }
    }
  }
  flushBullets();
  return result;
}

// Dark function signature block
function FuncSigBlock({ sig }) {
  const m = sig.match(/^(\w+)\(([^)]*)\)(?:\s*->\s*(.+))?$/);
  if (!m) return (
    <div className="docai-sig-block">
      <span className="docai-sig-kw">def </span>
      <span className="docai-sig-raw">{sig}</span>
    </div>
  );
  const [, name, params, ret] = m;
  const paramList = params ? splitParams(params) : [];
  return (
    <div className="docai-sig-block">
      <span className="docai-sig-kw">def </span>
      <span className="docai-sig-fn">{name}</span>
      <span className="docai-sig-punct">(</span>
      {paramList.map((p, i) => (
        <span key={i}>
          <span className="docai-sig-arg">{p}</span>
          {i < paramList.length - 1 && <span className="docai-sig-punct">, </span>}
        </span>
      ))}
      <span className="docai-sig-punct">)</span>
      {ret && (
        <>
          <span className="docai-sig-punct"> → </span>
          <span className="docai-sig-ret">{ret}</span>
        </>
      )}
    </div>
  );
}

// Extract function name only
function getFuncName(sig) {
  return sig.match(/^(\w+)/)?.[1] ?? sig;
}

// ===== Main Component =====
export default function DocAIResultPanel({ markdownText }) {
  const [activeTab, setActiveTab] = useState('imports');
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [openImports, setOpenImports] = useState(new Set());

  const parsed = useMemo(() => parseMarkdown(markdownText), [markdownText]);

  useEffect(() => {
    if (parsed.funcs.length > 0) {
      setActiveTab('funcs');
      setSelectedIdx(0);
    } else {
      setActiveTab('imports');
      setSelectedIdx(null);
    }
    setOpenImports(new Set());
  }, [markdownText]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedFunc = activeTab === 'funcs' && selectedIdx !== null
    ? (parsed.funcs[selectedIdx] ?? null)
    : null;

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setSelectedIdx(null);
  };

  const toggleImport = (i) => {
    setOpenImports(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <div className="docai-root">

      {/* ===== 左パネル ===== */}
      <div className="docai-left-panel">
        <div className="docai-left-header">
          <div className="docai-tab-row">
            <button
              className={`docai-tab-btn${activeTab === 'imports' ? ' docai-tab-btn-active' : ''}`}
              onClick={() => handleTabChange('imports')}
            >
              インポート
            </button>
            <button
              className={`docai-tab-btn${activeTab === 'funcs' ? ' docai-tab-btn-active' : ''}`}
              onClick={() => handleTabChange('funcs')}
            >
              関数
            </button>
          </div>
        </div>

        <div className="docai-list-body">
          {activeTab === 'imports' ? (
            parsed.imports.length === 0 ? (
              <div className="docai-list-empty">項目なし</div>
            ) : (
              parsed.imports.map((imp, i) => {
                const isOpen = openImports.has(i);
                return (
                  <div key={i} className="docai-import-accordion">
                    <button
                      className={`docai-import-accordion-header${isOpen ? ' docai-import-accordion-open' : ''}`}
                      onClick={() => toggleImport(i)}
                    >
                      <span className="docai-import-accordion-name">{imp.name}</span>
                      <span className="docai-import-accordion-chevron">{isOpen ? '▲' : '▼'}</span>
                    </button>
                    {isOpen && (
                      <div className="docai-import-accordion-body">
                        {imp.desc}
                      </div>
                    )}
                  </div>
                );
              })
            )
          ) : (
            parsed.funcs.length === 0 ? (
              <div className="docai-list-empty">項目なし</div>
            ) : (
              parsed.funcs.map((func, i) => (
                <div
                  key={i}
                  className={`docai-func-item${selectedIdx === i ? ' docai-func-item-active' : ''}`}
                  onClick={() => setSelectedIdx(i)}
                >
                  <div className="docai-func-item-name">
                    <span className="docai-func-item-fn">{getFuncName(func.sig)}</span>
                  </div>
                  {func.purpose && (
                    <div className="docai-func-item-purpose">{func.purpose}</div>
                  )}
                </div>
              ))
            )
          )}
        </div>
      </div>

      {/* ===== 中央パネル ===== */}
      <div className="docai-center-panel">
        {!selectedFunc ? (
          <div className="docai-empty">
            <div className="docai-empty-icon">⚙️</div>
            <div className="docai-empty-text">
              左の「関数」タブから<br />確認したい関数を選択してください
            </div>
          </div>
        ) : (
          <>
            {/* シグネチャヘッダー */}
            <div className="docai-sig-header">
              <FuncSigBlock sig={selectedFunc.sig} />
            </div>

            {/* 詳細ボディ */}
            <div className="docai-center-body">

              {/* 処理目的 */}
              {selectedFunc.purpose && (
                <div className="docai-section">
                  <div className="docai-section-title">
                    <span className="docai-section-icon docai-icon-purpose">目</span>
                    処理目的
                  </div>
                  <div className="docai-purpose-text">{renderInline(selectedFunc.purpose)}</div>
                </div>
              )}

              {/* 入力 */}
              <div className="docai-section">
                <div className="docai-section-title">
                  <span className="docai-section-icon docai-icon-input">入</span>
                  入力パラメータ
                </div>
                {selectedFunc.inputs.length === 0 ? (
                  <div className="docai-no-item">パラメータはありません</div>
                ) : (
                  <div className="docai-table-wrap">
                    <table className="docai-param-table">
                      <thead>
                        <tr><th>引数名</th><th>説明</th></tr>
                      </thead>
                      <tbody>
                        {selectedFunc.inputs.map((p, i) => (
                          <tr key={i}>
                            <td className="docai-param-name-cell">
                              <span className="docai-param-name">{p.name}</span>
                            </td>
                            <td className="docai-param-desc">{renderInline(p.desc)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* 出力 */}
              <div className="docai-section">
                <div className="docai-section-title">
                  <span className="docai-section-icon docai-icon-output">出</span>
                  出力
                </div>
                {selectedFunc.outputs.length === 0 ? (
                  <div className="docai-no-item">
                    戻り値はありません。結果はDBおよびAzureファイル共有に直接登録されます。
                  </div>
                ) : (
                  <div className="docai-table-wrap">
                    <table className="docai-param-table">
                      <thead>
                        <tr><th>型</th><th>説明</th></tr>
                      </thead>
                      <tbody>
                        {selectedFunc.outputs.map((p, i) => (
                          <tr key={i}>
                            <td className="docai-param-name-cell">
                              <span className="docai-param-name">{p.name}</span>
                            </td>
                            <td className="docai-param-desc">{renderInline(p.desc)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* アルゴリズム */}
              {selectedFunc.steps.length > 0 && (
                <div className="docai-section">
                  <div className="docai-section-title">
                    <span className="docai-section-icon docai-icon-algo">手</span>
                    アルゴリズム
                  </div>
                  <ol className="docai-step-list">
                    {selectedFunc.steps.map((step, i) => (
                      <li key={i} className="docai-step-item">
                        <span className="docai-step-badge">{i + 1}</span>
                        <span className="docai-step-text">{renderStepText(step)}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

            </div>
          </>
        )}
      </div>

    </div>
  );
}
