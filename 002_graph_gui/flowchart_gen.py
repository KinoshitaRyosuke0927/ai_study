# flowchart_gen.py
"""
Pythonコードからフローチャートを生成するモジュール

機能:
- 関数の制御フローをAST解析
- フローチャートのノードとエッジを生成
- Cytoscape形式でデータを出力

拡張:
- match-case (Python 3.10+) を "スイッチ型" ノード(kind="match")として表現
- case数が多い場合のレイアウト最適化ヒント(layout_hints)を付与
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

import azure_ai_operation_service


# ----------------------------
# フローグラフのデータ構造
# ----------------------------
@dataclass
class Node:
    """フローチャートのノード"""
    id: str        # ノードID
    label: str     # 表示ラベル
    kind: str      # ノード種別: start | process | decision | match | return


@dataclass
class Edge:
    """フローチャートのエッジ（矢印）"""
    id: str
    source: str
    target: str
    label: str = ""          # Yes/No, case xxx など
    weight: Optional[int] = None  # dagre最適化用ヒント（大きいほど優先）
    minlen: Optional[int] = None  # dagre最適化用ヒント（大きいほど距離を取る）


# フローチャートのノード出口を表現: (ノードID, エッジラベル)
Exit = Tuple[str, str]


class IdGen:
    """ID生成器（ノードとエッジ用）"""

    def __init__(self) -> None:
        self.n = 0
        self.e = 0

    def node(self) -> str:
        self.n += 1
        return f"n{self.n}"

    def edge(self) -> str:
        self.e += 1
        return f"e{self.e}"


# ----------------------------
# AST -> Flow builder
# ----------------------------
class FlowBuilder:
    """
    AST（抽象構文木）からフローチャートを構築するクラス

    設計方針:
    - then/elseの中間ノードは作成しない
    - if文(decision)から分岐先の先頭ノードへYes/Noエッジを接続
    - 分岐先が空の場合は、decisionから次の文へ直接エッジを接続（出口として保持）
    - endノードは作成しない（最後の出口は未接続のまま）
    - match-caseは "match" ノード1つから複数caseへ分岐する（switch型）
    - case数が多い場合のため、レイアウト最適化用ヒントを収集する
    """

    # caseが多いときに「switchとしてLR方向にしたい」などのヒントを出す閾値
    SWITCH_CASE_THRESHOLD = 6

    def __init__(self, func_name: str) -> None:
        self.ids = IdGen()
        self.nodes: List[Node] = []
        self.edges: List[Edge] = []
        self.func_name = func_name

        # 描画側で参照できる最適化ヒント
        self.layout_hints: Dict[str, Any] = {
            "switch_nodes": [],  # [{match_node_id, case_count, suggested_rankDir, case_order_labels}]
        }

    def add_node(self, label: str, kind: str) -> str:
        nid = self.ids.node()
        self.nodes.append(Node(id=nid, label=label, kind=kind))
        return nid

    def add_edge(
        self,
        source: str,
        target: str,
        label: str = "",
        weight: Optional[int] = None,
        minlen: Optional[int] = None,
    ) -> None:
        eid = self.ids.edge()
        self.edges.append(
            Edge(id=eid, source=source, target=target, label=label, weight=weight, minlen=minlen)
        )

    # ----------------------------
    # label helpers
    # ----------------------------
    def stmt_label(self, stmt: ast.stmt) -> Tuple[str, str]:
        """
        文からラベルとノード種別を取得
        Returns: (label, kind)
        """
        if isinstance(stmt, ast.Return):
            value = ast.unparse(stmt.value) if stmt.value is not None else ""
            label = f"return {value}".strip()
            return (label, "return")

        if isinstance(stmt, ast.Assign):
            targets = ", ".join(ast.unparse(t) for t in stmt.targets)
            val = ast.unparse(stmt.value)
            return (f"{targets} = {val}", "process")

        if isinstance(stmt, ast.AnnAssign):
            target = ast.unparse(stmt.target)
            ann = ast.unparse(stmt.annotation) if stmt.annotation else ""
            val = ast.unparse(stmt.value) if stmt.value else ""
            if val:
                return (f"{target}: {ann} = {val}", "process")
            return (f"{target}: {ann}", "process")

        if isinstance(stmt, ast.Expr):
            return (ast.unparse(stmt.value), "process")

        return (ast.dump(stmt, include_attributes=False), "process")

    def _is_match_stmt(self, stmt: ast.stmt) -> bool:
        # Python 3.10+ only
        return hasattr(ast, "Match") and isinstance(stmt, ast.Match)  # type: ignore[attr-defined]

    def _pattern_to_label(self, pattern: Any) -> str:
        """
        match_case.pattern を表示用ラベルにする
        - ast.MatchAs(name=None, pattern=None) は "default(_)" として扱う（case _）
        - それ以外は ast.unparse で文字列化
        """
        # case _:
        if hasattr(ast, "MatchAs") and isinstance(pattern, ast.MatchAs):  # type: ignore[attr-defined]
            if pattern.name is None and pattern.pattern is None:
                return "default"
        try:
            return ast.unparse(pattern)
        except Exception:
            # unparseできないパターンもあるので保険
            return repr(pattern)

    def _case_sort_key(self, case_obj: Any) -> Tuple[int, str]:
        """
        caseの順序をできるだけ見やすくするためのキー
        ざっくり:
        - default(case _) を最後
        - guardありを後ろ寄せ
        - それ以外は文字列順
        """
        pat = getattr(case_obj, "pattern", None)
        guard = getattr(case_obj, "guard", None)
        pat_label = self._pattern_to_label(pat)
        is_default = 1 if pat_label == "default" else 0
        has_guard = 1 if guard is not None else 0
        # defaultは最後(1)、guardありも後ろ(1)
        return (is_default, has_guard, pat_label)

    # ----------------------------
    # builders
    # ----------------------------
    def build_block(self, stmts: List[ast.stmt], incoming: List[Exit]) -> List[Exit]:
        """
        文のシーケンスからフローチャートブロックを構築
        Args:
            stmts: AST文のリスト
            incoming: このブロックの最初の文に接続すべき出口のリスト
        Returns:
            ブロック実行後の出口リスト（非終端の場合）
        """
        exits: List[Exit] = incoming[:]

        for stmt in stmts:
            # if
            if isinstance(stmt, ast.If):
                exits = self.build_if(stmt, exits)
                continue

            # match-case
            if self._is_match_stmt(stmt):
                exits = self.build_match(stmt, exits)  # type: ignore[arg-type]
                continue

            # normal stmt
            label, kind = self.stmt_label(stmt)
            nid = self.add_node(label=label, kind=kind)

            for prev_id, edge_label in exits:
                self.add_edge(prev_id, nid, edge_label)

            exits = [] if kind == "return" else [(nid, "")]

        return exits

    def build_if(self, stmt_if: ast.If, incoming: List[Exit]) -> List[Exit]:
        cond = ast.unparse(stmt_if.test)
        decision_id = self.add_node(label=f"if {cond} ?", kind="decision")

        for prev_id, edge_label in incoming:
            self.add_edge(prev_id, decision_id, edge_label)

        if stmt_if.body:
            then_exits = self.build_block(stmt_if.body, [(decision_id, "Yes")])
        else:
            then_exits = [(decision_id, "Yes")]

        if stmt_if.orelse:
            else_exits = self.build_block(stmt_if.orelse, [(decision_id, "No")])
        else:
            else_exits = [(decision_id, "No")]

        return then_exits + else_exits

    def build_match(self, stmt_match: "ast.Match", incoming: List[Exit]) -> List[Exit]:
        """
        match-case を switch型として扱う

        - matchノード(kind="match") を1つ作成
        - incoming -> match
        - match -> 各case先頭ノード へ "case ..."/"default" ラベル付きエッジ
        - case本体が空なら、そのcaseは「何もしない」→ 次の文へ落ちる出口として保持
        - match は fallthrough しない（CやJSのswitchのようなbreak不要）ので、
          各case本体の出口はすべて「matchの後続」へ合流させる（出口リストとして返す）
        """
        subject = ast.unparse(stmt_match.subject)
        match_id = self.add_node(label=f"match {subject}", kind="match")

        for prev_id, edge_label in incoming:
            self.add_edge(prev_id, match_id, edge_label)

        # case順序を整形（default最後、guard後ろ寄せ）
        cases = list(stmt_match.cases)
        cases_sorted = sorted(cases, key=self._case_sort_key)

        case_labels_for_hint: List[str] = []
        exits: List[Exit] = []

        # 多caseのときはdagreに「枝を広げたい」ヒントを入れる
        # （描画側が weight/minlen を参照してdagreへ渡す前提）
        case_count = len(cases_sorted)
        is_many = case_count >= self.SWITCH_CASE_THRESHOLD

        # dagreの経験則:
        # - edge.weight: 大きいほどそのエッジを優先的に近づける（交差を減らす方向に働くことがある）
        # - edge.minlen: 大きいほど距離を開ける（caseが多い時に詰まりにくい）
        # ここでは、caseが多い場合に minlen を少し大きくし、順序の一貫性のため weight を付ける
        for idx, case_obj in enumerate(cases_sorted):
            pat_label = self._pattern_to_label(case_obj.pattern)

            # guard がある場合は "case X if Y"
            if case_obj.guard is not None:
                guard_label = ast.unparse(case_obj.guard)
                edge_label = f"case {pat_label} if {guard_label}"
            else:
                edge_label = "default" if pat_label == "default" else f"case {pat_label}"

            case_labels_for_hint.append(edge_label)

            # case本体
            if case_obj.body:
                # match -> case先頭ノード へ直結 (build_block の incoming に edge_label を渡す)
                branch_exits = self.build_block(case_obj.body, [(match_id, edge_label)])
            else:
                # 空case: match から「次の文」へ edge_label で落ちる出口として保持
                branch_exits = [(match_id, edge_label)]

            # case本体の出口（returnしなかった出口）は matchの次へ合流させるため返す
            exits.extend(branch_exits)

            # 追加のdagreヒント（case多い場合のみ）
            # ※build_block は match_id から最初の文へエッジを張るとき add_edge() を呼ぶ。
            #   そこでweight/minlenを付与するには出口構造を拡張する必要があるため、
            #   ここでは "layout_hints" として描画側へ「このmatchは多caseである」情報を渡す。
            #   もしあなたの描画側が edge.label を見て該当エッジに weight/minlen を与えられるなら、
            #   その実装が最もシンプルです。

        if is_many:
            # 描画側に「このmatchはLR方向が見やすい」などのヒントを渡す
            self.layout_hints["switch_nodes"].append(
                {
                    "match_node_id": match_id,
                    "case_count": case_count,
                    # 全体レイアウトTBのままでも、switch部分だけLRにしたいニーズが強いのでヒント化
                    "suggested_rankDir": "LR",
                    "case_order_labels": case_labels_for_hint,
                    # 目安: caseが多いときは枝を広げる
                    "suggested_nodeSep": 70,
                    "suggested_rankSep": 90,
                }
            )

        return exits

    def build(self, stmts: List[ast.stmt]) -> Tuple[List[Node], List[Edge], Dict[str, Any]]:
        """
        関数本体からフローチャートを構築
        Returns:
            (nodes, edges, layout_hints)
        """
        start = self.add_node(label=f"Start: {self.func_name}()", kind="start")
        _exits = self.build_block(stmts, [(start, "")])
        return self.nodes, self.edges, self.layout_hints


# ----------------------------
# public functions
# ----------------------------
def extract_first_function(code: str) -> ast.FunctionDef:
    """
    コードから最初の関数定義を抽出
    """
    mod = ast.parse(code)
    for node in mod.body:
        if isinstance(node, ast.FunctionDef):
            return node
    raise ValueError("FunctionDef not found in given code.")


def build_cytoscape_elements(
    nodes: List[Node],
    edges: List[Edge],
    layout_hints: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    ノードとエッジのリストをCytoscape形式に変換
    - kind="match" を追加
    - layout_hints を meta として付与（描画側で最適化に使用）
    """
    elements: Dict[str, Any] = {
        "nodes": [{"data": {"id": n.id, "label": n.label, "kind": n.kind}} for n in nodes],
        "edges": [
            {
                "data": {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "label": e.label,
                    # dagre最適化用（描画側がcytoscape-dagreに渡すなら活用可）
                    **({} if e.weight is None else {"weight": e.weight}),
                    **({} if e.minlen is None else {"minlen": e.minlen}),
                }
            }
            for e in edges
        ],
    }
    if layout_hints:
        elements["meta"] = {"layout_hints": layout_hints}
    return elements


def generate_flowchart_data(code: str) -> Dict[str, Any]:
    """
    Pythonコードからフローチャートデータを生成（Cytoscape形式）

    Returns:
        {
          "nodes": [...],
          "edges": [...],
          "meta": {
            "layout_hints": {...}
          }
        }
    """
    try:
        func = extract_first_function(code)
        builder = FlowBuilder(func_name=func.name)
        nodes, edges, layout_hints = builder.build(func.body)

        elements = build_cytoscape_elements(nodes, edges, layout_hints)
        update_elements = azure_ai_operation_service.generate_flowchart_label(code, elements)
        return update_elements

    except Exception as e:
        raise ValueError(f"フローチャート生成エラー: {str(e)}")
