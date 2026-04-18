"""
Python AST解析による呼び出しグラフ生成

機能:
- Pythonソースコード（ファイルまたは文字列）を解析
- 関数定義を収集:
  - トップレベル関数: def foo(...)
  - クラスメソッド: class C: def m(...)
- 各関数本体から関数呼び出しを検出し、CALLエッジを作成
- rustworkx.PyDiGraphでグラフを構築
- node-link JSON形式でエクスポート（D3/Cytoscape等で使用可能）

制限事項（シンプルさを優先）:
- インポートや外部関数の完全な解決は行わない
- 名前解決は単純:
  - foo() -> "foo"
  - self.m() -> "ClassName.m" (メソッド内のみ)
  - C.m() -> "C.m" (クラス名リテラル)
  - ネスト関数は "outer.inner" として扱う
- 動的ディスパッチ、エイリアス、高階関数は未対応
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import rustworkx as rx


# ----------------------------
# データモデル
# ----------------------------
@dataclass(frozen=True)
class FunctionSymbol:
    """コードベースで定義された呼び出し可能なシンボル"""
    qname: str       # 修飾名（例: "foo", "Class.m", "outer.inner"）
    kind: str        # "function" または "method"
    lineno: int      # 開始行番号
    col: int         # 開始列番号
    end_lineno: int  # 終了行番号
    file: str        # ファイルパス


# ----------------------------
# AST訪問者クラス
# ----------------------------
class DefinitionCollector(ast.NodeVisitor):
    """
    関数定義とその本体を収集し、単純なスコープスタックを追跡
    
    生成するもの:
      - symbols: Dict[qname, FunctionSymbol] - 関数シンボル辞書
      - bodies: Dict[qname, ast.AST] - 関数本体のAST
      - imports: Dict[alias, module_name] - インポート情報
    """
    def __init__(self, file: str) -> None:
        self.file = file
        self.class_stack: List[str] = []  # クラス名のスタック
        self.func_stack: List[str] = []   # 関数名のスタック（ネスト追跡用）
        self.symbols: Dict[str, FunctionSymbol] = {}  # 修飾名 -> シンボル
        self.bodies: Dict[str, ast.AST] = {}  # 修飾名 -> AST本体
        self.imports: Dict[str, str] = {}  # エイリアス -> モジュール名

    def _current_prefix(self) -> str:
        """現在のスコープのプレフィックスを取得（Class.outer形式）"""
        parts = []
        parts.extend(self.class_stack)  # クラス名を先に
        parts.extend(self.func_stack)   # 次にネスト関数名
        return ".".join(parts) if parts else ""

    def _make_qname(self, name: str) -> str:
        """関数名から修飾名を生成"""
        prefix = self._current_prefix()
        return f"{prefix}.{name}" if prefix else name

    def visit_Import(self, node: ast.Import) -> Any:
        """import文を処理（例: import module as alias）"""
        for alias in node.names:
            module_name = alias.name
            as_name = alias.asname or alias.name
            self.imports[as_name] = module_name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        """from import文を処理（例: from module import name as alias）"""
        if node.module:
            for alias in node.names:
                if alias.name == '*':  # from module import * は無視
                    continue
                imported_name = alias.name
                as_name = alias.asname or alias.name
                # "module.name" の形式で保存
                self.imports[as_name] = f"{node.module}.{imported_name}"
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        """クラス定義を処理"""
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def _handle_function_def(self, node: ast.AST, name: str) -> None:
        """関数/メソッド定義の共通処理"""
        qname = self._make_qname(name)
        kind = "method" if self.class_stack else "function"
        lineno = getattr(node, "lineno", -1)
        col = getattr(node, "col_offset", -1)
        end_lineno = getattr(node, "end_lineno", lineno)

        # シンボル情報を記録
        self.symbols[qname] = FunctionSymbol(
            qname=qname, kind=kind, lineno=lineno, col=col, end_lineno=end_lineno, file=self.file
        )
        self.bodies[qname] = node

        # ネストした関数定義を追跡（関数内関数）
        self.func_stack.append(name)
        self.generic_visit(node)
        self.func_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """通常の関数定義を処理"""
        self._handle_function_def(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        """async関数定義を処理"""
        self._handle_function_def(node, node.name)


class CallCollector(ast.NodeVisitor):
    """
    関数本体内の呼び出しターゲットを収集（ベストエフォート）
    
    解決ルール:
      - foo() -> "foo"
      - self.m() (クラスC内) -> "C.m"
      - C.m() -> "C.m"
      - module.func() -> インポートされている場合は解決
      - ネストした呼び出し "inner()" は後で解決
    """
    def __init__(self, current_qname: str, imports: Dict[str, str] = None) -> None:
        self.current_qname = current_qname  # 現在解析している関数の修飾名
        self.calls: List[str] = []  # 呼び出しターゲットのリスト
        self.imports = imports or {}  # エイリアス -> モジュール名

        # 現在の関数がメソッドの場合、qnameからクラス名を推測
        # 例: "Class.method" または "Class.outer.inner"
        self.current_class: Optional[str] = None
        parts = current_qname.split(".")
        if len(parts) >= 2:
            # DefinitionCollectorでは、クラス修飾メソッドは常にクラス名で始まる
            self.current_class = parts[0]

    def visit_Call(self, node: ast.Call) -> Any:
        """関数呼び出しを処理"""
        target = self._extract_target(node.func)
        if target:
            self.calls.append(target)
        self.generic_visit(node)

    def _extract_target(self, func_expr: ast.AST) -> Optional[str]:
        """関数呼び出しのターゲットを抽出"""
        # ケース1: foo()
        if isinstance(func_expr, ast.Name):
            name = func_expr.id
            # インポートされたモジュール/関数かチェック
            if name in self.imports:
                return self.imports[name]
            return name

        # ケース2: obj.attr()
        if isinstance(func_expr, ast.Attribute):
            attr = func_expr.attr
            value = func_expr.value

            # self.m() -> クラス名が分かっていれば "Class.m"
            if isinstance(value, ast.Name) and value.id == "self" and self.current_class:
                return f"{self.current_class}.{attr}"

            # module.func() または Class.method()
            if isinstance(value, ast.Name):
                base_name = value.id
                # インポートされたモジュールかチェック
                if base_name in self.imports:
                    module_path = self.imports[base_name]
                    # "module.func" の形式で返す
                    return f"{module_path}.{attr}"
                # 直接クラス名の場合
                return f"{base_name}.{attr}"

            # something.more.m() -> 最小版では解決しない
            return None

        # ラムダ式などは処理しない
        return None


# ----------------------------
# グラフ構築 (rustworkx)
# ----------------------------
def build_call_graph_from_code(code: str, *, file: str = "<memory>") -> rx.PyDiGraph:
    """
    PythonコードからコールグラフをPyDiGraphとして構築
    
    Args:
        code: Pythonソースコード文字列
        file: ファイルパス（デバッグ用）
    
    Returns:
        関数ノードと呼び出しエッジを含むrustworkxのPyDiGraph
    """
    tree = ast.parse(code, filename=file)
    
    # ソースコードを行ごとに分割（コード抽出用）
    source_lines = code.split('\n')

    # 1) 関数定義を収集
    defs = DefinitionCollector(file=file)
    defs.visit(tree)
    
    # 2) グラフを初期化
    g = rx.PyDiGraph()
    node_id_by_qname: Dict[str, int] = {}

    # ノードを追加（関数定義のコードを抽出して保存）
    for qname, sym in defs.symbols.items():
        # 関数定義のコードを抽出（end_linenoを使用）
        code_snippet = extract_function_code(source_lines, sym.lineno, sym.end_lineno)
        
        nid = g.add_node(
            {
                "qname": sym.qname,
                "kind": sym.kind,
                "file": sym.file,
                "lineno": sym.lineno,
                "col": sym.col,
                "code": code_snippet  # コードを追加
            }
        )
        node_id_by_qname[qname] = nid

    # ヘルパー関数: 観測された呼び出し文字列を定義されたqnameにマッピング
    def resolve_call(callee: str, caller_qname: str) -> Optional[str]:
        """呼び出し文字列を解決して実際のqnameに変換"""
        # 直接一致
        if callee in defs.symbols:
            return callee

        # 呼び出し元がネストしている場合（例: outer.inner）
        # calleeが "x" なら、同じプレフィックス内を探す
        caller_parts = caller_qname.split(".")
        # スコープを徐々に狭めて試行: Class.outer.inner -> Class.outer -> Class
        for i in range(len(caller_parts), 0, -1):
            prefix = ".".join(caller_parts[:i])
            candidate = f"{prefix}.{callee}"
            if candidate in defs.symbols:
                return candidate

        # calleeが "Class.m" のような形式で定義されている場合
        if "." in callee and callee in defs.symbols:
            return callee

        # 解決不可（外部ライブラリまたは動的呼び出し）
        return None

    # エッジを追加
    seen_edges: set[Tuple[int, int]] = set()
    all_calls = []  # デバッグ用
    unresolved_calls = []  # 未解決の呼び出しを記録（ファイル間呼び出しの可能性）
    
    for caller_qname, body in defs.bodies.items():
        # 関数本体内の呼び出しを収集
        calls = CallCollector(current_qname=caller_qname, imports=defs.imports)
        calls.visit(body)
        
        if calls.calls:
            all_calls.extend([(caller_qname, c) for c in calls.calls])

        caller_id = node_id_by_qname[caller_qname]
        for callee_raw in calls.calls:
            callee_qname = resolve_call(callee_raw, caller_qname)
            if not callee_qname:
                # 未解決の呼び出しを記録（ファイル間呼び出しの可能性）
                unresolved_calls.append((caller_qname, callee_raw))
                continue

            callee_id = node_id_by_qname.get(callee_qname)
            if callee_id is None:
                # 定義が見つからない呼び出しも記録
                unresolved_calls.append((caller_qname, callee_raw))
                continue

            key = (caller_id, callee_id)
            if key in seen_edges:
                continue

            g.add_edge(
                caller_id,
                callee_id,
                {"kind": "CALLS", "from": caller_qname, "to": callee_qname},
            )
            seen_edges.add(key)
    
    # 未解決の呼び出しをグラフのメタデータとして保存
    g.attrs = {
        "unresolved_calls": unresolved_calls,
        "imports": defs.imports,
        "file": file
    }

    return g

def extract_function_code(source_lines: list, start_lineno: int, end_lineno: int) -> str:
    """関数定義のコードを抽出する（ASTのend_linenoを使用）
    
    Args:
        source_lines: ソースコードの行リスト
        start_lineno: 関数定義の開始行（1始まり）
        end_lineno: 関数定義の終了行（1始まり）
    
    Returns:
        関数定義のコード（前のコメントを含む、前後の空行を除く）
    """
    if start_lineno <= 0 or start_lineno > len(source_lines):
        return "# コードが見つかりません"
    
    # 行番号を配列インデックスに変換（1始まり→0始まり）
    start_idx = start_lineno - 1
    end_idx = min(end_lineno - 1, len(source_lines) - 1)
    
    # 関数定義の前のコメント行を探す
    comment_start = start_idx
    for i in range(start_idx - 1, -1, -1):
        line = source_lines[i].strip()
        if line.startswith('#'):
            comment_start = i
        elif line:  # 空行でない、コメントでもない行で終了
            break
        # 空行は継続
    
    # 前後の空行を除外してコードを抽出
    # 開始位置: コメント開始位置
    # 終了位置: end_idx（ASTが示す関数の終わり）
    code_lines = source_lines[comment_start:end_idx + 1]
    
    return '\n'.join(code_lines)

def build_call_graph_from_file(py_path: str | Path) -> rx.PyDiGraph:
    p = Path(py_path)
    code = p.read_text(encoding="utf-8")
    return build_call_graph_from_code(code, file=str(p))


# ----------------------------
# Export (node-link JSON)
# ----------------------------
def to_node_link_json(g: rx.PyDiGraph) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    for i in range(g.num_nodes()):
        data = g.get_node_data(i)
        if data is None:
            continue
        nodes.append({"id": i, **data})

    links: List[Dict[str, Any]] = []
    for u, v, data in g.weighted_edge_list():
        links.append(
            {
                "source": u,
                "target": v,
                **(data if isinstance(data, dict) else {"kind": "CALLS"}),
            }
        )

    return {"directed": True, "multigraph": False, "nodes": nodes, "links": links}


# ----------------------------
# CLI-ish runner (optional)
# ----------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build call graph from Python AST (rustworkx).")
    parser.add_argument("path", help="Target .py file")
    parser.add_argument("--out", default=None, help="Output JSON path (default: <stem>.callgraph.json)")
    args = parser.parse_args()

    g = build_call_graph_from_file(args.path)
    payload = to_node_link_json(g)

    out = Path(args.out) if args.out else Path(args.path).with_suffix("").with_name(Path(args.path).stem + ".callgraph.json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Nodes: {g.num_nodes()}, Edges: {g.num_edges()}")
    print(f"Wrote: {out}")
