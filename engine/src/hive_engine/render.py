"""Render a .pptx to per-slide PNGs: LibreOffice headless → PDF → PyMuPDF → PNG."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pymupdf as fitz

SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    shutil.which("soffice") or "",
]

# A dedicated LibreOffice profile so we never fight a desktop LibreOffice instance.
_LO_PROFILE = Path(tempfile.gettempdir()) / "hive_lo_profile"


def find_soffice() -> str:
    for c in SOFFICE_CANDIDATES:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("LibreOffice not found — `brew install --cask libreoffice`")


def render_pptx(pptx: Path, out_dir: Path, dpi: int = 110) -> tuple[list[Path], dict[str, float]]:
    """Returns (png paths in slide order, timings in seconds)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    subprocess.run(
        [find_soffice(), f"-env:UserInstallation=file://{_LO_PROFILE}", "--headless",
         "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    t1 = time.perf_counter()
    pdf = out_dir / (pptx.stem + ".pdf")
    pngs: list[Path] = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc):
            p = out_dir / f"slide-{i}.png"
            page.get_pixmap(dpi=dpi).save(p)
            pngs.append(p)
    t2 = time.perf_counter()
    return pngs, {"pdf": t1 - t0, "png": t2 - t1, "total": t2 - t0}
