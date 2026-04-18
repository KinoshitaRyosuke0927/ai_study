from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path
from typing import Any, Iterable, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox

import libcst as cst
from libcst import CSTNode


# -----------------------------
# Mermaid builder
# -----------------------------
def _escape_label(s: str) -> str:
    # Mermaid node labels are easiest in quotes; escape quotes and newlines
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MermaidGraph:
    def __init__(self) -> None:
        self.lines: list[str] = ["```mermaid", "graph TD"]
        self._next_id = 0

    def new_id(self) -> str:
        self._next_id += 1
        return f"N{self._next_id}"

    def add_node(self, node_id: str, label: str) -> None:
        self.lines.append(f'  {node_id}["{_escape_label(label)}"]')

    def add_edge(self, parent_id: str, child_id: str, edge_label: str | None = None) -> None:
        if edge_label:
            self.lines.append(f'  {parent_id} -- "{_escape_label(edge_label)}" --> {child_id}')
        else:
            self.lines.append(f"  {parent_id} --> {child_id}")

    def finish(self) -> str:
        return "\n".join(self.lines + ["```", ""])


# -----------------------------
# AST -> Mermaid
# -----------------------------
def _ast_children(node: ast.AST) -> Iterable[Tuple[str, Any]]:
    # yields (field_name, value)
    for name, value in ast.iter_fields(node):
        yield name, value


def _ast_label(node: ast.AST) -> str:
    # show key info for readability
    t = type(node).__name__
    if isinstance(node, ast.Name):
        return f"{t}(id={node.id})"
    if isinstance(node, ast.arg):
        return f"{t}({node.arg})"
    if isinstance(node, ast.Constant):
        return f"{t}({repr(node.value)})"
    if isinstance(node, ast.Attribute):
        return f"{t}(attr={node.attr})"
    if isinstance(node, ast.FunctionDef):
        return f"{t}(name={node.name})"
    if isinstance(node, ast.ClassDef):
        return f"{t}(name={node.name})"
    if isinstance(node, ast.Call):
        return f"{t}()"
    return t


def ast_to_mermaid(tree: ast.AST, max_depth: int | None = None) -> str:
    g = MermaidGraph()

    def walk(n: ast.AST, parent_id: str | None = None, edge_label: str | None = None, depth: int = 0) -> None:
        if max_depth is not None and depth > max_depth:
            return
            
        my_id = g.new_id()
        g.add_node(my_id, _ast_label(n))
        if parent_id:
            g.add_edge(parent_id, my_id, edge_label)

        # 深度制限に達した場合は子ノードを省略
        if max_depth is not None and depth >= max_depth:
            if any(isinstance(v, (ast.AST, list)) for _, v in _ast_children(n)):
                truncated_id = g.new_id()
                g.add_node(truncated_id, "...")
                g.add_edge(my_id, truncated_id, "truncated")
            return

        for field, value in _ast_children(n):
            if isinstance(value, ast.AST):
                walk(value, my_id, field, depth + 1)
            elif isinstance(value, list):
                # create a list container node only if it has AST children
                ast_items = [v for v in value if isinstance(v, ast.AST)]
                if not ast_items:
                    continue
                list_id = g.new_id()
                g.add_node(list_id, f"list({field})[{len(ast_items)}]")
                g.add_edge(my_id, list_id, field)
                for i, item in enumerate(ast_items):
                    walk(item, list_id, str(i), depth + 2)
            else:
                # omit primitive fields to keep the graph compact
                pass

    walk(tree)
    return g.finish()


# -----------------------------
# CST (LibCST) -> Mermaid
# -----------------------------
def _is_cst_node(x: Any) -> bool:
    return isinstance(x, CSTNode)


def _cst_label(node: CSTNode) -> str:
    # LibCST nodes have plenty of detail; type name is usually enough
    return type(node).__name__


def _cst_fields(node: CSTNode) -> Iterable[Tuple[str, Any]]:
    # LibCST nodes are dataclasses; introspect fields
    for f in dataclasses.fields(node):
        yield f.name, getattr(node, f.name)


def cst_to_mermaid(module: cst.Module, *, include_trivia: bool = False, max_depth: int | None = None) -> str:
    """
    include_trivia=False: whitespace/comment-only nodes are largely suppressed by ignoring
    primitives and empty lists. Still, LibCST has many small nodes; the output can be big.
    """
    g = MermaidGraph()

    def walk(n: CSTNode, parent_id: str | None = None, edge_label: str | None = None, depth: int = 0) -> None:
        if max_depth is not None and depth > max_depth:
            return
            
        my_id = g.new_id()
        g.add_node(my_id, _cst_label(n))
        if parent_id:
            g.add_edge(parent_id, my_id, edge_label)

        # 深度制限に達した場合は子ノードを省略
        if max_depth is not None and depth >= max_depth:
            if any(_is_cst_node(v) or (isinstance(v, (list, tuple)) and any(_is_cst_node(x) for x in v)) for _, v in _cst_fields(n)):
                truncated_id = g.new_id()
                g.add_node(truncated_id, "...")
                g.add_edge(my_id, truncated_id, "truncated")
            return

        for field, value in _cst_fields(n):
            if _is_cst_node(value):
                walk(value, my_id, field, depth + 1)
            elif isinstance(value, (list, tuple)):
                cst_items = [v for v in value if _is_cst_node(v)]
                if not cst_items:
                    continue
                list_id = g.new_id()
                g.add_node(list_id, f"list({field})[{len(cst_items)}]")
                g.add_edge(my_id, list_id, field)
                for i, item in enumerate(cst_items):
                    walk(item, list_id, str(i), depth + 2)
            else:
                # primitives/trivia: optionally show some
                if include_trivia and value not in (None, "", (), []):
                    prim_id = g.new_id()
                    g.add_node(prim_id, f"{field}={repr(value)}")
                    g.add_edge(my_id, prim_id, field)

    walk(module)
    return g.finish()


# -----------------------------
# D3.js JSON builder
# -----------------------------
def ast_to_d3_json(tree: ast.AST, max_depth: int | None = None) -> dict:
    """ASTをD3.js Collapsible Tree用のJSON形式に変換"""
    
    def walk(n: ast.AST, depth: int = 0) -> dict:
        node = {
            "name": _ast_label(n),
            "children": []
        }
        
        if max_depth is not None and depth >= max_depth:
            if any(isinstance(v, (ast.AST, list)) for _, v in _ast_children(n)):
                node["children"].append({"name": "..."})
            return node
        
        for field, value in _ast_children(n):
            if isinstance(value, ast.AST):
                child = walk(value, depth + 1)
                child["name"] = f"{field}: {child['name']}"
                node["children"].append(child)
            elif isinstance(value, list):
                ast_items = [v for v in value if isinstance(v, ast.AST)]
                if ast_items:
                    list_node = {
                        "name": f"{field}[{len(ast_items)}]",
                        "children": [walk(item, depth + 2) for item in ast_items]
                    }
                    node["children"].append(list_node)
        
        if not node["children"]:
            del node["children"]
        
        return node
    
    return walk(tree)


def cst_to_d3_json(module: cst.Module, max_depth: int | None = None) -> dict:
    """CSTをD3.js Collapsible Tree用のJSON形式に変換"""
    
    def walk(n: CSTNode, depth: int = 0) -> dict:
        node = {
            "name": _cst_label(n),
            "children": []
        }
        
        if max_depth is not None and depth >= max_depth:
            if any(_is_cst_node(v) or (isinstance(v, (list, tuple)) and any(_is_cst_node(x) for x in v)) 
                   for _, v in _cst_fields(n)):
                node["children"].append({"name": "..."})
            return node
        
        for field, value in _cst_fields(n):
            if _is_cst_node(value):
                child = walk(value, depth + 1)
                child["name"] = f"{field}: {child['name']}"
                node["children"].append(child)
            elif isinstance(value, (list, tuple)):
                cst_items = [v for v in value if _is_cst_node(v)]
                if cst_items:
                    list_node = {
                        "name": f"{field}[{len(cst_items)}]",
                        "children": [walk(item, depth + 2) for item in cst_items]
                    }
                    node["children"].append(list_node)
        
        if not node["children"]:
            del node["children"]
        
        return node
    
    return walk(module)


def generate_d3_html(json_data: dict, title: str) -> str:
    """D3.js Collapsible TreeのHTMLファイルを生成"""
    html_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            text-align: center;
            color: #333;
        }}
        #tree-container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
            overflow: auto;
        }}
        .node circle {{
            fill: #fff;
            stroke: steelblue;
            stroke-width: 3px;
            cursor: pointer;
        }}
        .node circle.has-children {{
            fill: lightsteelblue;
        }}
        .node text {{
            font: 12px sans-serif;
            cursor: pointer;
        }}
        .link {{
            fill: none;
            stroke: #ccc;
            stroke-width: 2px;
        }}
        .instructions {{
            text-align: center;
            color: #666;
            margin-bottom: 10px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="instructions">
        ノードをクリックして展開/折りたたみできます
    </div>
    <div id="tree-container"></div>
    
    <script>
        const treeDataJson = {json_data};
        
        const width = window.innerWidth - 80;
        const height = window.innerHeight - 200;
        
        const svg = d3.select("#tree-container")
            .append("svg")
            .attr("width", width)
            .attr("height", height)
            .append("g")
            .attr("transform", "translate(40,20)");
        
        const treemap = d3.tree().size([height - 40, width - 200]);
        
        let root = d3.hierarchy(treeDataJson);
        root.x0 = height / 2;
        root.y0 = 0;
        
        let i = 0;
        
        // 初期状態で一部を折りたたむ
        if (root.children) {{
            root.children.forEach(collapse);
        }}
        
        update(root);
        
        function collapse(d) {{
            if (d.children) {{
                d._children = d.children;
                d._children.forEach(collapse);
                d.children = null;
            }}
        }}
        
        function update(source) {{
            const treeData = treemap(root);
            const nodes = treeData.descendants();
            const links = treeData.descendants().slice(1);
            
            nodes.forEach(d => {{ d.y = d.depth * 180; }});
            
            const node = svg.selectAll("g.node")
                .data(nodes, d => d.id || (d.id = ++i));
            
            const nodeEnter = node.enter().append("g")
                .attr("class", "node")
                .attr("transform", d => `translate(${{source.y0}},${{source.x0}})`)
                .on("click", click);
            
            nodeEnter.append("circle")
                .attr("r", 1e-6)
                .attr("class", d => d._children ? "has-children" : "");
            
            nodeEnter.append("text")
                .attr("dy", ".35em")
                .attr("x", d => d.children || d._children ? -13 : 13)
                .attr("text-anchor", d => d.children || d._children ? "end" : "start")
                .text(d => d.data.name);
            
            const nodeUpdate = nodeEnter.merge(node);
            
            nodeUpdate.transition()
                .duration(750)
                .attr("transform", d => `translate(${{d.y}},${{d.x}})`);
            
            nodeUpdate.select("circle")
                .attr("r", 6)
                .attr("class", d => d._children ? "has-children" : "");
            
            const nodeExit = node.exit().transition()
                .duration(750)
                .attr("transform", d => `translate(${{source.y}},${{source.x}})`)
                .remove();
            
            nodeExit.select("circle").attr("r", 1e-6);
            nodeExit.select("text").style("fill-opacity", 1e-6);
            
            const link = svg.selectAll("path.link")
                .data(links, d => d.id);
            
            const linkEnter = link.enter().insert("path", "g")
                .attr("class", "link")
                .attr("d", d => {{
                    const o = {{x: source.x0, y: source.y0}};
                    return diagonal(o, o);
                }});
            
            const linkUpdate = linkEnter.merge(link);
            
            linkUpdate.transition()
                .duration(750)
                .attr("d", d => diagonal(d, d.parent));
            
            link.exit().transition()
                .duration(750)
                .attr("d", d => {{
                    const o = {{x: source.x, y: source.y}};
                    return diagonal(o, o);
                }})
                .remove();
            
            nodes.forEach(d => {{
                d.x0 = d.x;
                d.y0 = d.y;
            }});
        }}
        
        function diagonal(s, d) {{
            return `M ${{s.y}} ${{s.x}}
                    C ${{(s.y + d.y) / 2}} ${{s.x}},
                      ${{(s.y + d.y) / 2}} ${{d.x}},
                      ${{d.y}} ${{d.x}}`;
        }}
        
        function click(event, d) {{
            if (d.children) {{
                d._children = d.children;
                d.children = null;
            }} else {{
                d.children = d._children;
                d._children = null;
            }}
            update(d);
        }}
    </script>
</body>
</html>"""
    
    return html_template.format(
        title=title,
        json_data=json.dumps(json_data, ensure_ascii=False, indent=2)
    )


# -----------------------------
# Main tool flow
# -----------------------------
def run_tool() -> None:
    print("=" * 60)
    print("AST/CST Mermaid Tool 起動中...")
    print("=" * 60)
    
    root = tk.Tk()
    root.withdraw()
    
    # ウィンドウを前面に表示
    root.lift()
    root.attributes('-topmost', True)
    root.after(100, lambda: root.attributes('-topmost', False))

    print("\n[1/4] Pythonファイルを選択してください...")
    print("      ※ファイル選択ダイアログが表示されています")
    
    file_path = filedialog.askopenfilename(
        title="Pythonファイル（.py）を選択してください",
        filetypes=[("Python files", "*.py")],
    )
    if not file_path:
        print("\n処理がキャンセルされました。")
        return
    
    print(f"      選択されたファイル: {file_path}")

    print("\n[2/4] 出力形式を選択してください...")
    print("      ※ダイアログが表示されています")
    
    # 出力形式の選択（MermaidまたはD3.js）
    use_mermaid = messagebox.askyesno(
        "出力形式の選択",
        "出力形式を選択してください\n\n"
        "【はい】 Mermaid (Markdown形式・軽量)\n"
        "【いいえ】 D3.js (HTML形式・インタラクティブ)"
    )
    
    output_format = "mermaid" if use_mermaid else "d3"
    print(f"      選択された形式: {'Mermaid' if use_mermaid else 'D3.js'}")

    print("\n[3/4] 深度制限を選択してください...")
    print("      ※深度制限選択ダイアログが表示されています")
    
    # 深度制限の選択
    depth_choice = messagebox.askyesnocancel(
        "深度制限",
        "ツリーの深度を制限しますか？\n\n"
        "はい: 深度10に制限（推奨・図が見やすくなります）\n"
        "いいえ: 制限なし（全体を出力）\n"
        "キャンセル: 処理を中止"
    )
    if depth_choice is None:  # キャンセル
        print("\n処理がキャンセルされました。")
        return
    
    max_depth = 10 if depth_choice else None
    depth_msg = f"深度{max_depth}に制限" if max_depth else "制限なし"
    print(f"      選択された深度: {depth_msg}")

    print("\n[4/4] ファイルを解析して出力中...")
    
    path = Path(file_path)
    try:
        code = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # fallback (Windows環境など)
        code = path.read_text(encoding="utf-8-sig")

    # 出力先をツール自体のある階層に変更
    out_dir = Path(__file__).parent
    stem = path.stem

    output_files = []

    # 1) AST
    print("      - AST解析中...")
    try:
        tree = ast.parse(code, filename=str(path))
        
        if output_format == "mermaid":
            print("        Mermaid形式に変換中...")
            ast_md = ast_to_mermaid(tree, max_depth=max_depth)
            ast_out = out_dir / f"{stem}.AST.mmd.md"
            ast_out.write_text(ast_md, encoding="utf-8")
            output_files.append(ast_out.name)
        else:  # d3
            print("        D3.js (HTML)形式に変換中...")
            json_data = ast_to_d3_json(tree, max_depth=max_depth)
            html_content = generate_d3_html(json_data, f"AST: {stem}")
            ast_out = out_dir / f"{stem}.AST.html"
            ast_out.write_text(html_content, encoding="utf-8")
            output_files.append(ast_out.name)
        
        print(f"        ✓ AST出力完了: {output_files[-1]}")
            
    except SyntaxError as e:
        error_msg = f"AST解析に失敗しました:\n{e}"
        print(f"\nエラー: {error_msg}")
        messagebox.showerror("構文エラー", error_msg)
        return
    except Exception as e:
        error_msg = f"AST出力に失敗しました:\n{e}"
        print(f"\nエラー: {error_msg}")
        messagebox.showerror("AST出力エラー", error_msg)
        return

    # 2) CST (LibCST)
    print("      - CST解析中...")
    try:
        module = cst.parse_module(code)
        
        if output_format == "mermaid":
            print("        Mermaid形式に変換中...")
            cst_md = cst_to_mermaid(module, include_trivia=False, max_depth=max_depth)
            cst_out = out_dir / f"{stem}.CST.mmd.md"
            cst_out.write_text(cst_md, encoding="utf-8")
            output_files.append(cst_out.name)
        else:  # d3
            print("        D3.js (HTML)形式に変換中...")
            json_data = cst_to_d3_json(module, max_depth=max_depth)
            html_content = generate_d3_html(json_data, f"CST: {stem}")
            cst_out = out_dir / f"{stem}.CST.html"
            cst_out.write_text(html_content, encoding="utf-8")
            output_files.append(cst_out.name)
        
        print(f"        ✓ CST出力完了: {output_files[-1]}")
            
    except Exception as e:
        error_msg = f"CST解析に失敗しました:\n{e}"
        print(f"\nエラー: {error_msg}")
        messagebox.showerror("CST解析エラー", error_msg)
        return

    format_name = "Mermaid (Markdown)" if output_format == "mermaid" else "D3.js (HTML)"

    depth_info = f"（深度制限: {max_depth}）" if max_depth else "（深度制限なし）"
    
    file_list = "\n".join(f"- {f}" for f in output_files)
    
    print("\n" + "=" * 60)
    print("✓ 処理が完了しました！")
    print("=" * 60)
    print(f"出力形式: {format_name} {depth_info}")
    print(f"出力先: {out_dir}")
    print(f"\n出力ファイル:")
    for f in output_files:
        print(f"  - {f}")
    print("=" * 60)
    
    messagebox.showinfo(
        "完了",
        f"出力しました [{format_name}] {depth_info}:\n\n"
        f"{file_list}\n\n"
        f"出力先: {out_dir}"
    )


if __name__ == "__main__":
    run_tool()