"""
Pythonファイルを解析してCytoscape形式のグラフJSONを生成する統合スクリプト

使い方:
    python analyze_and_visualize.py <python_file_or_directory> [--out <output_json>]

例:
    python analyze_and_visualize.py data/login_service.py
    python analyze_and_visualize.py src/  # フォルダ内の全.pyファイル
    python analyze_and_visualize.py data/login_service.py --out data/graph.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Dict

import rustworkx as rx

from generate_graph_json import build_call_graph_from_file, to_node_link_json


def collect_python_files(path: Path) -> List[Path]:
    """
    パスからPythonファイルを収集
    
    Args:
        path: ファイルまたはディレクトリのパス
    
    Returns:
        Pythonファイルのリスト
    """
    if path.is_file():
        if path.suffix == '.py':
            return [path]
        else:
            return []
    elif path.is_dir():
        return sorted(path.rglob('*.py'))
    else:
        return []


def merge_graphs(graphs: List[rx.PyDiGraph]) -> rx.PyDiGraph:
    """
    複数のグラフを1つに統合
    
    Args:
        graphs: マージするグラフのリスト
    
    Returns:
        統合されたグラフ
    """
    if not graphs:
        return rx.PyDiGraph()
    
    if len(graphs) == 1:
        return graphs[0]
    
    merged = rx.PyDiGraph()
    qname_to_node_id = {}
    
    # 全グラフのノードを追加（qnameで重複排除）
    for g in graphs:
        for i in range(g.num_nodes()):
            data = g.get_node_data(i)
            if data is None:
                continue
            
            qname = data.get("qname")
            if not qname:
                continue
            
            # 既に同じqnameのノードがあればスキップ
            if qname in qname_to_node_id:
                continue
            
            node_id = merged.add_node(data)
            qname_to_node_id[qname] = node_id
    
    # 全グラフのエッジを追加（重複排除）
    seen_edges = set()
    for g in graphs:
        for src, tgt, edge_data in g.weighted_edge_list():
            src_data = g.get_node_data(src)
            tgt_data = g.get_node_data(tgt)
            
            if not src_data or not tgt_data:
                continue
            
            src_qname = src_data.get("qname")
            tgt_qname = tgt_data.get("qname")
            
            if not src_qname or not tgt_qname:
                continue
            
            # マージ後のグラフでのノードIDを取得
            if src_qname not in qname_to_node_id or tgt_qname not in qname_to_node_id:
                continue
            
            new_src = qname_to_node_id[src_qname]
            new_tgt = qname_to_node_id[tgt_qname]
            
            edge_key = (new_src, new_tgt)
            if edge_key in seen_edges:
                continue
            
            merged.add_edge(new_src, new_tgt, edge_data)
            seen_edges.add(edge_key)
    
    return merged


def resolve_cross_file_calls(graphs: List[rx.PyDiGraph], py_files: List[Path], base_dir: Path = None) -> rx.PyDiGraph:
    """
    複数のグラフを統合し、ファイル間の関数呼び出しも解決
    
    Args:
        graphs: 各ファイルのグラフのリスト
        py_files: 解析したPythonファイルのリスト
        base_dir: ベースディレクトリ（相対パス計算用）
    
    Returns:
        統合されたグラフ（ファイル間呼び出しも含む）
    """
    if not graphs:
        return rx.PyDiGraph()
    
    if len(graphs) == 1:
        return graphs[0]
    
    # ベースディレクトリが指定されていない場合は共通の親ディレクトリを使用
    if base_dir is None and py_files:
        base_dir = py_files[0].parent
        for py_file in py_files[1:]:
            # より浅い共通の親を見つける
            while not str(py_file).startswith(str(base_dir)):
                base_dir = base_dir.parent
    
    # まず基本的なマージを実行
    merged = rx.PyDiGraph()
    qname_to_node_id = {}
    file_to_qnames = {}  # 正規化されたファイルパス -> そのファイルで定義されているqnameのリスト
    
    # ファイル名からモジュール名を推測するマッピング
    # インポート情報を使って、ファイル名 -> 実際のモジュールパス を推測
    filename_to_module = {}  # 例: "db_access_service.py" -> "database.db_access_service"
    
    # 各グラフのインポート情報を収集して、ファイル名とモジュール名の関係を学習
    for g, py_file in zip(graphs, py_files):
        if not hasattr(g, 'attrs') or 'imports' not in g.attrs:
            continue
        
        imports = g.attrs['imports']
        # インポート例: "db_access_service" -> "database.db_access_service"
        # これから "db_access_service" というファイルは "database.db_access_service" というモジュール名であることが分かる
        for alias, full_module in imports.items():
            # full_module が "database.db_access_service" の場合
            # 最後の部分 "db_access_service" がファイル名に対応する可能性が高い
            if '.' in full_module:
                module_parts = full_module.split('.')
                last_part = module_parts[-1]  # 例: "db_access_service"
                
                # このlast_partに対応するファイルを探す
                for pf in py_files:
                    if pf.stem == last_part:
                        filename_to_module[pf.stem] = full_module
                        break
    
    # デバッグ: ファイル名→モジュール名マッピングを表示
    if filename_to_module:
        print(f"  ファイル名→モジュール名マッピング: {len(filename_to_module)} エントリ")
        for fname, mname in list(filename_to_module.items())[:5]:
            print(f"    {fname} -> {mname}")
    
    # モジュール名マッピングを構築（従来の方法と併用）
    file_to_module = {}
    module_to_file = {}
    for py_file in py_files:
        file_stem = py_file.stem
        
        # インポート情報から学習したモジュール名を優先
        if file_stem in filename_to_module:
            module_name = filename_to_module[file_stem]
        else:
            # フォールバック: ベースディレクトリからの相対パスを使用
            try:
                if base_dir:
                    rel_path = py_file.relative_to(base_dir)
                else:
                    rel_path = py_file
            except ValueError:
                rel_path = py_file
            
            # モジュール名を構築（例: services/login_service.py -> services.login_service）
            parts = rel_path.parts
            module_parts = []
            for part in parts:
                if part.endswith('.py'):
                    module_parts.append(part[:-3])  # .py を除去
                else:
                    module_parts.append(part)
            
            module_name = '.'.join(module_parts)
        
        file_str = str(py_file)
        file_to_module[file_str] = module_name
        module_to_file[module_name] = file_str
        
        # ファイル名だけでもマッピング（from filename import funcのケース）
        file_base = py_file.stem
        if file_base not in module_to_file:
            module_to_file[file_base] = file_str
    
    # デバッグ: ファイル→モジュール名マッピングを表示
    print(f"  ファイル→モジュールマッピング:")
    for py_file in py_files:
        file_str = str(py_file)
        module_name = file_to_module.get(file_str, "unknown")
        print(f"    {py_file.name} -> {module_name}")
    
    # 全グラフのノードを追加
    for g in graphs:
        for i in range(g.num_nodes()):
            data = g.get_node_data(i)
            if data is None:
                continue
            
            qname = data.get("qname")
            file_path = data.get("file")
            if not qname:
                continue
            
            # 既に同じqnameのノードがあればスキップ
            if qname in qname_to_node_id:
                continue
            
            node_id = merged.add_node(data)
            qname_to_node_id[qname] = node_id
            
            # ファイルごとのqnameリストを記録
            if file_path:
                if file_path not in file_to_qnames:
                    file_to_qnames[file_path] = []
                file_to_qnames[file_path].append(qname)
    
    # qname -> ファイルパスのマッピングも作成
    qname_to_file = {}
    for file_path, qnames in file_to_qnames.items():
        for qname in qnames:
            qname_to_file[qname] = file_path
    
    # モジュール名.関数名 -> qname のマッピング
    module_func_to_qname = {}
    for file_path, qnames in file_to_qnames.items():
        # ファイルパスからモジュール名を取得
        module_name = file_to_module.get(file_path)
        if not module_name:
            continue
        
        for qname in qnames:
            # 1. 完全修飾名: module.func
            full_key = f"{module_name}.{qname}"
            module_func_to_qname[full_key] = qname
            
            # 2. モジュール階層の各レベルでもマッピング
            # 例: database.db_access_service.select_user
            #  -> db_access_service.select_user, select_user でも解決可能に
            module_parts = module_name.split('.')
            for i in range(len(module_parts)):
                partial_module = '.'.join(module_parts[i:])
                partial_key = f"{partial_module}.{qname}"
                if partial_key not in module_func_to_qname:
                    module_func_to_qname[partial_key] = qname
            
            # 3. 関数名だけでも解決できるようにする（衝突がない場合のみ）
            if qname not in module_func_to_qname:
                module_func_to_qname[qname] = qname
            
            # 4. モジュール名の短縮形も追加
            # 例: "database.db_access_service" の場合、"db_access_service.select_user" も登録
            if len(module_parts) > 0:
                last_part = module_parts[-1]
                short_key = f"{last_part}.{qname}"
                if short_key not in module_func_to_qname:
                    module_func_to_qname[short_key] = qname
    
    # デバッグ: マッピング情報を出力
    if module_func_to_qname:
        print(f"  モジュール関数マッピング: {len(module_func_to_qname)} エントリ")
        # サンプルを表示（database、services関連を優先表示）
        sample_keys = []
        for key in module_func_to_qname.keys():
            if 'database' in key or 'service' in key:
                sample_keys.append(key)
                if len(sample_keys) >= 10:
                    break
        for key in sample_keys:
            print(f"    {key} -> {module_func_to_qname[key]}")
    
    # 全グラフのエッジを追加（ファイル間呼び出しも解決）
    seen_edges = set()
    cross_file_edges = 0
    
    # まず既存のエッジを追加
    for g in graphs:
        for src, tgt, edge_data in g.weighted_edge_list():
            src_data = g.get_node_data(src)
            tgt_data = g.get_node_data(tgt)
            
            if not src_data or not tgt_data:
                continue
            
            src_qname = src_data.get("qname")
            tgt_qname = tgt_data.get("qname")
            
            if not src_qname or not tgt_qname:
                continue
            
            # マージ後のグラフでのノードIDを取得
            if src_qname not in qname_to_node_id or tgt_qname not in qname_to_node_id:
                continue
            
            new_src = qname_to_node_id[src_qname]
            new_tgt = qname_to_node_id[tgt_qname]
            
            edge_key = (new_src, new_tgt)
            if edge_key in seen_edges:
                continue
            
            merged.add_edge(new_src, new_tgt, edge_data)
            seen_edges.add(edge_key)
    
    # 未解決の呼び出しを処理してファイル間エッジを追加
    total_unresolved = 0
    for g in graphs:
        if not hasattr(g, 'attrs') or 'unresolved_calls' not in g.attrs:
            continue
        
        unresolved_calls = g.attrs['unresolved_calls']
        total_unresolved += len(unresolved_calls)
    
    if total_unresolved > 0:
        print(f"  未解決呼び出し総数: {total_unresolved} 件")
        print(f"  解決を試行中...")
    
    resolved_count = 0
    for g in graphs:
        if not hasattr(g, 'attrs') or 'unresolved_calls' not in g.attrs:
            continue
        
        unresolved_calls = g.attrs['unresolved_calls']
        
        for caller_qname, callee_raw in unresolved_calls:
            # 呼び出し元のノードIDを取得
            if caller_qname not in qname_to_node_id:
                continue
            
            new_src = qname_to_node_id[caller_qname]
            new_tgt = None
            resolved_qname = None
            
            # モジュール修飾名で解決を試みる
            if callee_raw in module_func_to_qname:
                resolved_qname = module_func_to_qname[callee_raw]
                if resolved_qname in qname_to_node_id:
                    new_tgt = qname_to_node_id[resolved_qname]
                    resolved_count += 1
                    if resolved_count <= 5:  # 最初の5件だけ詳細表示
                        print(f"    ✓ {caller_qname} -> {callee_raw} => {resolved_qname}")
            
            if new_tgt is None:
                continue
            
            edge_key = (new_src, new_tgt)
            if edge_key in seen_edges:
                continue
            
            # ファイル間呼び出しエッジを追加
            merged.add_edge(
                new_src,
                new_tgt,
                {"kind": "CALLS", "from": caller_qname, "to": resolved_qname}
            )
            seen_edges.add(edge_key)
            cross_file_edges += 1
    
    if total_unresolved > 0:
        print(f"  解決成功: {resolved_count}/{total_unresolved} 件")
    if cross_file_edges > 0:
        print(f"  ファイル間エッジ: {cross_file_edges} 個追加")
    
    return merged


def analyze_and_convert(
    py_path: str | Path,
    out_path: str | Path | None = None
) -> Path:
    """
    Pythonファイルまたはディレクトリを解析してCytoscape形式のJSONを生成
    
    Args:
        py_path: 解析対象のPythonファイルまたはディレクトリパス
        out_path: 出力先JSONファイルパス (デフォルト: data/graph.json)
    
    Returns:
        出力先のPathオブジェクト
    """
    py_path = Path(py_path)
    
    if out_path is None:
        out_path = Path(__file__).parent / "data" / "graph.json"
    else:
        out_path = Path(out_path)
    
    # 1. Pythonファイルを収集
    py_files = collect_python_files(py_path)
    
    if not py_files:
        print(f"警告: Pythonファイルが見つかりませんでした: {py_path}")
        # 空のグラフを出力
        cytoscape_data = {"elements": {"nodes": [], "edges": []}}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(cytoscape_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return out_path
    
    print(f"解析対象: {len(py_files)} ファイル")
    
    # 2. 各ファイルを解析してグラフを生成
    graphs = []
    for py_file in py_files:
        try:
            print(f"  {py_file.name}")
            graph = build_call_graph_from_file(py_file)
            graphs.append(graph)
            
            # 簡潔な情報表示
            unresolved_count = 0
            if hasattr(graph, 'attrs') and 'unresolved_calls' in graph.attrs:
                unresolved_count = len(graph.attrs['unresolved_calls'])
            
            print(f"    ノード: {graph.num_nodes()}, エッジ: {graph.num_edges()}, 未解決: {unresolved_count}")
            
        except Exception as e:
            print(f"  警告: {py_file} の解析に失敗しました: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # 3. グラフを統合（ファイル間の呼び出しも解決）
    # ベースディレクトリを決定
    base_dir = py_path if py_path.is_dir() else py_path.parent
    print(f"\n統合処理:")
    merged_graph = resolve_cross_file_calls(graphs, py_files, base_dir)
    node_link_data = to_node_link_json(merged_graph)
    
    print(f"\n統合結果: ノード: {merged_graph.num_nodes()}, エッジ: {merged_graph.num_edges()}")
    
    # 4. Cytoscape形式に変換
    cytoscape_data = convert_to_cytoscape_format(node_link_data)
    
    # 5. JSONファイルとして保存
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(cytoscape_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"出力完了: {out_path}")
    return out_path


def convert_to_cytoscape_format(node_link_data: dict) -> dict:
    """
    node-link形式のJSONをCytoscape形式に変換
    
    Args:
        node_link_data: {"nodes": [...], "links": [...]} 形式のデータ
    
    Returns:
        {"elements": {"nodes": [...], "edges": [...]}} 形式のデータ
    """
    nodes = []
    for n in node_link_data.get("nodes", []):
        nid = str(n["id"])
        label = n.get("qname") or n.get("name") or nid
        nodes.append({
            "data": {
                "id": nid,
                "label": label,
                **{k: v for k, v in n.items() if k not in ("id",)}
            }
        })
    
    edges = []
    for i, e in enumerate(node_link_data.get("links", []), start=1):
        src = str(e["source"])
        tgt = str(e["target"])
        kind = e.get("kind", "CALLS")
        edges.append({
            "data": {
                "id": f"e{i}",
                "source": src,
                "target": tgt,
                "label": kind,
                **{k: v for k, v in e.items() if k not in ("source", "target")}
            }
        })
    
    return {"elements": {"nodes": nodes, "edges": edges}}


def main():
    parser = argparse.ArgumentParser(
        description="Pythonファイルまたはディレクトリを解析してCytoscape形式のグラフJSONを生成"
    )
    parser.add_argument(
        "path",
        help="解析対象のPythonファイルまたはディレクトリパス"
    )
    parser.add_argument(
        "--out",
        default=None,
        help="出力先JSONファイルパス (デフォルト: data/graph.json)"
    )
    
    args = parser.parse_args()
    
    analyze_and_convert(args.path, args.out)


if __name__ == "__main__":
    main()
