from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

try:
    from pdf2image import convert_from_path
    _PDF2IMAGE_AVAILABLE = True
except ImportError:
    _PDF2IMAGE_AVAILABLE = False

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
    システムから LibreOffice の実行ファイルパスを探して返す

    Returns
    -----------------
    - path: str,    LibreOffice 実行ファイルのパス

    """
    for candidate in _SOFFICE_CANDIDATES:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "LibreOffice が見つかりません。インストール後に PATH を通してください。\n"
        "  Ubuntu: sudo apt install libreoffice\n"
        "  Windows: https://www.libreoffice.org/download/"
    )


def convert_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> Path:
    """
    PPTX を LibreOffice で PDF に変換し PDF パスを返す

    Args
    -----------------
    - pptx_path: Path,      変換対象の PPTX ファイルパス
    - output_dir: Path,     PDF の出力先ディレクトリ

    Returns
    -----------------
    - pdf_path: Path,       変換後の PDF ファイルパス

    """
    soffice = _find_soffice()
    # 並列リクエスト時の LibreOffice プロファイル競合を避けるため作業ディレクトリ専用プロファイルを使う
    profile_uri = (output_dir / "lo_profile").as_uri()
    try:
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
    PDF を各ページ PNG/JPEG に変換しスライドごとの辞書リストを返す

    Args
    -----------------
    - pdf_path: Path,           変換対象の PDF ファイルパス
    - output_dir: Path,         画像の出力先ディレクトリ
    - dpi: int,                 出力解像度（デフォルト: 200 DPI）
    - jpeg_quality: int,        JPEG 品質（デフォルト: 75）

    Returns
    -----------------
    - slide_images: list[dict[str, Path]],  スライドごとの PNG/JPEG パスを格納した辞書リスト

    """
    if not _PDF2IMAGE_AVAILABLE:
        raise RuntimeError(
            "pdf2image がインストールされていません。pip install pdf2image を実行してください。\n"
            "また Poppler (pdftoppm) のインストールも必要です。\n"
            "  Ubuntu: sudo apt install poppler-utils\n"
            "  Windows: https://github.com/oschwartz10612/poppler-windows/releases/"
        )

    # PNG/JPEG の出力ディレクトリを作成
    png_dir = output_dir / "png"
    jpg_dir = output_dir / "jpg"
    png_dir.mkdir(exist_ok=True)
    jpg_dir.mkdir(exist_ok=True)

    # PDF を PIL Image のリストに変換
    try:
        pages = convert_from_path(str(pdf_path), dpi=dpi)
    except Exception as exc:
        raise RuntimeError(
            f"PDF から画像への変換に失敗しました (Poppler が必要です): {exc}"
        ) from exc

    if not pages:
        raise RuntimeError("PDF からスライド画像を生成できませんでした（スライドが0枚）")

    ## ページごとに PNG/JPEG として保存
    slide_images: list[dict[str, Path]] = []
    for i, page in enumerate(pages, start=1):
        png_path = png_dir / f"slide_{i}.png"
        jpg_path = jpg_dir / f"slide_{i}.jpg"
        page.save(str(png_path), "PNG")
        page.save(str(jpg_path), "JPEG", quality=jpeg_quality, optimize=True)
        slide_images.append({"png": png_path, "jpg": jpg_path})

    return slide_images


def render_pptx_to_images(
    file_bytes: bytes,
    work_dir: Path,
    dpi: int = _PNG_DPI,
    jpeg_quality: int = _JPEG_QUALITY,
) -> list[dict[str, Path]]:
    """
    PPTX バイト列を受け取りスライドごとの PNG/JPEG パスリストを返す

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
    # PPTX バイト列をファイルに書き出してから変換
    pptx_path = work_dir / "input.pptx"
    pptx_path.write_bytes(file_bytes)
    pdf_path = convert_pptx_to_pdf(pptx_path, work_dir)
    return convert_pdf_to_images(pdf_path, work_dir, dpi, jpeg_quality)


def images_to_base64_dict(slide_images: list[dict[str, Path]]) -> list[dict[str, str]]:
    """
    スライド画像パスを Base64 文字列の辞書リストに変換する

    Args
    -----------------
    - slide_images: list[dict[str, Path]],  スライドごとの PNG/JPEG パスを格納した辞書リスト

    Returns
    -----------------
    - result: list[dict[str, str]],         スライドごとの PNG/JPEG Base64 文字列を格納した辞書リスト

    """
    return [
        {
            "png": base64.b64encode(item["png"].read_bytes()).decode(),
            "jpg": base64.b64encode(item["jpg"].read_bytes()).decode(),
        }
        for item in slide_images
    ]
