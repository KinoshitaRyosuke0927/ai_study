"""
FastAPI ベースのグラフ可視化サーバー

機能:
- Pythonファイルのアップロードと解析
- 呼び出しグラフの生成とCytoscape形式での提供
- フローチャート生成API
- 静的ファイル（HTML/JS）の配信
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from analyze_and_visualize import analyze_and_convert
from flowchart_gen import generate_flowchart_data

APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "data" / "graph.json"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Graph GUI (Cytoscape.js)")

# 静的ファイルの配信
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    """ルートパス - index.htmlを返す"""
    return FileResponse(STATIC_DIR / "index.html")


def _load_graph() -> Dict[str, Any]:
    """保存されたグラフデータを読み込む"""
    if not DATA_PATH.exists():
        # ファイルがない場合は空のグラフを返す
        return {"elements": {"nodes": [], "edges": []}}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _save_graph(payload: Dict[str, Any]) -> None:
    """グラフデータをJSONファイルに保存"""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/graph")
def get_graph():
    """保存されているグラフデータを取得"""
    return JSONResponse(_load_graph())


@app.post("/api/graph")
def save_graph(payload: Dict[str, Any]):
    """グラフデータを保存"""
    # 基本的なバリデーション
    if "elements" not in payload or "nodes" not in payload["elements"] or "edges" not in payload["elements"]:
        raise HTTPException(status_code=400, detail="Invalid payload. Expected {elements:{nodes:[], edges:[]}}")
    _save_graph(payload)
    return {"ok": True, "path": str(DATA_PATH)}

@app.post("/api/analyze")
async def analyze_python_file(file: UploadFile = File(...)):
    """
    単一のPythonファイルをアップロードして解析
    
    Args:
        file: アップロードされたPythonファイル
    
    Returns:
        解析結果とグラフデータ
    """
    # ファイルタイプをチェック
    if not file.filename.endswith('.py'):
        raise HTTPException(status_code=400, detail="Pythonファイル (.py) のみアップロード可能です")
    
    # 一時ファイルとして保存
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.py', delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    
    try:
        # 解析実行
        analyze_and_convert(tmp_path, DATA_PATH)
        
        # 生成されたグラフを読み込んで返却
        graph_data = _load_graph()
        
        return {
            "ok": True,
            "filename": file.filename,
            "files": 1,
            "nodes": len(graph_data.get("elements", {}).get("nodes", [])),
            "edges": len(graph_data.get("elements", {}).get("edges", [])),
            "graph": graph_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析エラー: {str(e)}")
    finally:
        # 一時ファイルを削除
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/api/analyze-multiple")
async def analyze_multiple_files(files: List[UploadFile] = File(...)):
    """
    複数のPythonファイルをアップロードして解析し、統合されたグラフを生成
    
    Args:
        files: アップロードされた複数のPythonファイル
    
    Returns:
        解析結果と統合されたグラフデータ
    """
    if not files:
        raise HTTPException(status_code=400, detail="ファイルが選択されていません")
    
    # Pythonファイルのみフィルタ
    py_files = [f for f in files if f.filename.endswith('.py')]
    if not py_files:
        raise HTTPException(status_code=400, detail="Pythonファイル (.py) が含まれていません")
    
    # 一時ディレクトリを作成
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # 全ファイルを一時ディレクトリに保存（ディレクトリ構造を保持）
        for file in py_files:
            tmp_path = temp_dir / file.filename
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            content = await file.read()
            tmp_path.write_bytes(content)
        
        # ディレクトリ全体を解析（ファイル間の呼び出しも解決）
        analyze_and_convert(temp_dir, DATA_PATH)
        
        # 生成されたグラフを読み込んで返却
        graph_data = _load_graph()
        
        return {
            "ok": True,
            "files": len(py_files),
            "filenames": [f.filename for f in py_files],
            "nodes": len(graph_data.get("elements", {}).get("nodes", [])),
            "edges": len(graph_data.get("elements", {}).get("edges", [])),
            "graph": graph_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析エラー: {str(e)}")
    finally:
        # 一時ファイルとディレクトリを削除
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@app.get("/api/flowchart/{identifier}")
async def get_cached_flowchart(identifier: str):
    """
    保存されているフローチャートデータを取得
    
    Args:
        identifier: フローチャートの識別子（qname_lineno形式）
    
    Returns:
        保存されているフローチャートデータ、または404エラー
    """
    flowchart_path = APP_DIR / "data" / "flowcharts" / f"{identifier}.json"
    
    if not flowchart_path.exists():
        raise HTTPException(status_code=404, detail="フローチャートが見つかりません")
    
    try:
        flowchart_data = json.loads(flowchart_path.read_text(encoding="utf-8"))
        return {
            "ok": True,
            "flowchart": flowchart_data,
            "cached": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"フローチャート読み込みエラー: {str(e)}")


@app.post("/api/flowchart")
async def generate_flowchart(payload: Dict[str, Any]):
    """
    Pythonコードからフローチャートを生成
    
    Args:
        payload: {"code": "...", "identifier": "..."} の形式
    
    Returns:
        フローチャートのCytoscapeデータ
    """
    code = payload.get("code", "")
    identifier = payload.get("identifier", "")
    
    if not code:
        raise HTTPException(status_code=400, detail="コードが指定されていません")
    
    try:
        flowchart_data = generate_flowchart_data(code)
        
        # 識別子が指定されている場合はデータを保存
        if identifier:
            flowchart_dir = APP_DIR / "data" / "flowcharts"
            flowchart_dir.mkdir(parents=True, exist_ok=True)
            flowchart_path = flowchart_dir / f"{identifier}.json"
            flowchart_path.write_text(
                json.dumps(flowchart_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        
        return {
            "ok": True,
            "flowchart": flowchart_data,
            "cached": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"フローチャート生成エラー: {str(e)}")
