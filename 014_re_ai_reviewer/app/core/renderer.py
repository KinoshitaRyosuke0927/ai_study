from __future__ import annotations

import base64
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
_JPEG_QUALITY = 75


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


def convert_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> Path:
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


def convert_pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = _PNG_DPI,
    jpeg_quality: int = _JPEG_QUALITY,
) -> list[dict[str, Path]]:
    """
    PDFをページごとにPNG/JPEGに変換して, スライドごとの辞書リストを返す

    Args
    -----------------
    - pdf_path: Path,           変換対象のPDFファイルパス
    - output_dir: Path,         画像の出力先ディレクトリ
    - dpi: int,                 出力解像度(デフォルト: 200 DPI)
    - jpeg_quality: int,        JPEG 品質(デフォルト: 75)

    Returns
    -----------------
    - slide_images: list[dict[str, Path]],  スライドごとのPNG/JPEGパスを格納した辞書リスト

    """
    # PNG/JPEGの出力ディレクトリを作成
    png_dir = output_dir / "png"
    jpg_dir = output_dir / "jpg"
    png_dir.mkdir(exist_ok=True)
    jpg_dir.mkdir(exist_ok=True)

    # PDFをPIL Imageのリストに変換
    try:
        # PDFを画像に変換
        pages = convert_from_path(str(pdf_path), dpi=dpi)
    except Exception as exc:
        raise RuntimeError(f"PDF から画像への変換に失敗しました (Poppler が必要です): {exc}") from exc

    # 変換に失敗した場合
    if not pages:
        raise RuntimeError("PDF からスライド画像を生成できませんでした（スライドが0枚）")

    ## ページごとにPNG/JPEGとして保存
    # 入れ物用意
    slide_images: list[dict[str, Path]] = []
    # ページごとに処理
    for i, page in enumerate(pages, start=1):
        # 保存先のパスを作成
        png_path = png_dir / f"slide_{i}.png"
        jpg_path = jpg_dir / f"slide_{i}.jpg"
        # 画像を保存
        page.save(str(png_path), "PNG")
        page.save(str(jpg_path), "JPEG", quality=jpeg_quality, optimize=True)
        # 保存した画像の情報を追加
        slide_images.append({"png": png_path, "jpg": jpg_path})

    return slide_images


def render_pptx_to_images(
    file_bytes: bytes,
    work_dir: Path,
    dpi: int = _PNG_DPI,
    jpeg_quality: int = _JPEG_QUALITY,
) -> list[dict[str, Path]]:
    """
    PPTXバイト列を受け取りスライドごとのPNG/JPEGパスリストを返す

    Args
    -----------------
    - file_bytes: bytes,        PPTXファイルのバイト列
    - work_dir: Path,           作業ディレクトリのパス
    - dpi: int,                 出力解像度（デフォルト: 200 DPI）
    - jpeg_quality: int,        JPEG 品質（デフォルト: 75）

    Returns
    -----------------
    - slide_images: list[dict[str, Path]],  スライドごとの PNG/JPEG パスを格納した辞書リスト

    """
    ## PPTX バイト列をファイルに書き出してから変換
    # PowerPointを一時保存
    pptx_path = work_dir / "input.pptx"
    pptx_path.write_bytes(file_bytes)
    # PowerPointをPDFに変換
    pdf_path = convert_pptx_to_pdf(pptx_path, work_dir)
    # PDFをページごとに画像に変換して返却
    return convert_pdf_to_images(pdf_path, work_dir, dpi, jpeg_quality)


def images_to_base64_dict(slide_images: list[dict[str, Path]]) -> list[dict[str, str]]:
    """
    スライド画像パスをBase64文字列の辞書リストに変換する

    Args
    -----------------
    - slide_images: list[dict[str, Path]],  スライドごとのPNG/JPEGパスを格納した辞書リスト

    Returns
    -----------------
    - result: list[dict[str, str]],         スライドごとのPNG/JPEG Base64文字列を格納した辞書リスト

    """
    return [
        {
            "png": base64.b64encode(item["png"].read_bytes()).decode(),
            "jpg": base64.b64encode(item["jpg"].read_bytes()).decode(),
        }
        for item in slide_images
    ]
