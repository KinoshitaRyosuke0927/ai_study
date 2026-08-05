from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pdf2image import convert_from_path

# LibreOffice の実行ファイル候補パスリスト
_SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/libreoffice",
    "/usr/bin/soffice",
    "/usr/local/bin/libreoffice",
]

_PNG_DPI = 200


def _find_soffice() -> str:
    """
    システムからLibreOfficeの実行ファイルパスを探して返す

    Returns
    -----------------
    - path: str,    LibreOffice実行ファイルのパス

    """
    # LibreOfficeがインストールされているであろうパスを順番に検索
    for candidate in _SOFFICE_CANDIDATES:
        # LibreOfficeが見つかった場合
        if shutil.which(candidate) or Path(candidate).exists():
            # パスを返却
            return candidate

    # LibreOfficeが見つけられなかった場合
    raise RuntimeError(
        "LibreOffice が見つかりません。インストール後に PATH を通してください。\n"
        "  Ubuntu: sudo apt install libreoffice\n"
        "  Windows: https://www.libreoffice.org/download/"
    )


def _convert_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> Path:
    """
    PowerPointファイルをLibreOfficeでPDFに変換してPDFのパスを返す

    Args
    -----------------
    - pptx_path: Path,      変換対象のPPTXファイルパス
    - output_dir: Path,     PDFの出力先ディレクトリ

    Returns
    -----------------
    - pdf_path: Path,       変換後のPDFファイルパス

    """
    # LibreOfficeのパスを検索
    soffice = _find_soffice()
    # 並列リクエスト時のLibreOfficeプロファイル競合を避けるため, 作業ディレクトリ専用プロファイルを使う
    profile_uri = (output_dir / "lo_profile").as_uri()
    try:
        # LibreOfficeでPDF化実行
        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--norestore",
                f"-env:UserInstallation={profile_uri}",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                str(pptx_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    # エラーになった場合は, エラーごとにメッセージ返却
    except FileNotFoundError as exc:
        raise RuntimeError(f"LibreOffice 実行ファイルが起動できません: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("LibreOffice の PDF 変換がタイムアウトしました（120秒）") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"LibreOffice の PDF 変換が失敗しました\n"
            f"stdout: {exc.stdout}\nstderr: {exc.stderr}"
        ) from exc

    # 変換後の PDF ファイルが存在するか確認
    pdf_path = output_dir / (pptx_path.stem + ".pdf")
    # PDF変換に失敗した場合はエラーを返却
    if not pdf_path.exists():
        raise RuntimeError(
            f"PDF 変換後にファイルが見つかりません: {pdf_path}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return pdf_path


def render_pptx_first_slide_to_png(pptx_bytes: bytes, work_dir: Path, dpi: int = _PNG_DPI) -> bytes:
    """
    アップロードされたpptxを, LibreOfficeでPDF化した上でpdf2imageにより
    1枚目のスライドのみをPNG画像に変換する

    Args
    -----------------
    - pptx_bytes: bytes,    アップロードされたpptxファイルのバイト列
    - work_dir: Path,       作業ディレクトリのパス
    - dpi: int,             出力解像度（デフォルト: 200 DPI）

    Returns
    -----------------
    - image_bytes: bytes,   1枚目のスライドのPNG画像バイト列

    """
    # PPTX バイト列をファイルに書き出してから変換
    pptx_path = work_dir / "input.pptx"
    pptx_path.write_bytes(pptx_bytes)

    # PowerPointをPDFに変換
    pdf_path = _convert_pptx_to_pdf(pptx_path, work_dir)

    # PDFの1ページ目のみをPIL Imageに変換
    try:
        pages = convert_from_path(str(pdf_path), dpi=dpi, first_page=1, last_page=1)
    except Exception as exc:
        raise RuntimeError(f"PDF から画像への変換に失敗しました (Poppler が必要です): {exc}") from exc

    if not pages:
        raise RuntimeError("PDF からスライド画像を生成できませんでした（スライドが0枚）")

    png_path = work_dir / "slide_1.png"
    pages[0].save(str(png_path), "PNG")
    return png_path.read_bytes()
