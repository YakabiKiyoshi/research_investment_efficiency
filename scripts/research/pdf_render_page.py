"""pdf_render_page.py -- render page PNGs for sanctioned visual checks.

P1.5 table-verification route: structured table extraction (P2) is deferred
because PyMuPDF find_tables failed the 2026-07 feasibility test on real
finance/accounting PDFs (0 recall with the line strategies; the text
strategy grids whole prose pages and garbles minus signs). Until a reliable
extractor exists, table values seen in text packets may be cited ONLY after
visually matching them against a page PNG produced by this script.

Renders <out-root>/<paper_id>/renders/page-NNNN.png and records provenance
in renders/index.json. The source PDF's sha256 is re-verified against
manifest.json before rendering so a PNG can never silently come from a
different file than the ingested artifacts.

Usage:
    py scripts/research/pdf_render_page.py --paper Foo_2020_JAR --page 8
    py scripts/research/pdf_render_page.py --pdf docs/papers/Foo_2020_JAR.pdf --page 3-5
        [--out-root outputs/ai/pdf] [--dpi 200]

Prints one "RENDER: <path>" line per page as the last stdout lines.
Exit codes: 0 ok, 1 sha256 mismatch, 2 bad args/missing artifacts,
3 missing dependency.
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"


def eprint(*args):
    print(*args, file=sys.stderr)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    try:
        import fitz
    except ImportError:
        eprint("[render] missing dependency: pymupdf -- run: py -m pip install pymupdf")
        return 3

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="source PDF path (paper_id = file stem)")
    group.add_argument("--paper", help="paper_id (artifact dir name)")
    ap.add_argument("--page", required=True, help="page number or range, e.g. 8 or 3-5")
    ap.add_argument("--out-root", default="outputs/ai/pdf")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    m = re.match(r"^(\d+)(?:-(\d+))?$", args.page)
    if not m:
        eprint(f"[render] bad --page '{args.page}' (expected N or N-M)")
        return 2
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if lo < 1 or hi < lo:
        eprint(f"[render] bad page range {lo}-{hi}")
        return 2

    paper_id = args.paper if args.paper else Path(args.pdf).stem
    art_dir = Path(args.out_root) / paper_id
    manifest = load_json(art_dir / "manifest.json")
    if manifest is None:
        eprint(f"[render] no manifest.json for '{paper_id}' under {args.out_root}; "
               "run pdf_ingest.py first")
        return 2

    pdf_path = Path(args.pdf) if args.pdf else Path(manifest.get("source_pdf", ""))
    if not pdf_path.is_file():
        eprint(f"[render] source PDF not found: {pdf_path}")
        return 2
    actual_sha = sha256_of(pdf_path)
    expected_sha = manifest.get("source_sha256")
    if expected_sha and actual_sha != expected_sha:
        eprint(f"[render] sha256 mismatch: PDF {actual_sha[:12]}... vs manifest "
               f"{str(expected_sha)[:12]}...; artifacts are stale -- re-run pdf_ingest.py")
        return 1

    doc = fitz.open(str(pdf_path))
    if hi > doc.page_count:
        eprint(f"[render] page {hi} out of range (document has {doc.page_count} pages)")
        doc.close()
        return 2

    renders_dir = art_dir / "renders"
    index_path = renders_dir / "index.json"
    index = load_json(index_path) or {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": expected_sha or actual_sha,
        "renders": {},
    }
    out_paths = []
    for pno in range(lo, hi + 1):
        pix = doc[pno - 1].get_pixmap(dpi=args.dpi)
        png_path = renders_dir / f"page-{pno:04d}.png"
        renders_dir.mkdir(parents=True, exist_ok=True)
        pix.save(str(png_path))
        index["renders"][png_path.name] = {
            "page": pno,
            "dpi": args.dpi,
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        out_paths.append(png_path)
        print(f"[render] page {pno} -> {png_path} ({args.dpi} dpi)")
    doc.close()
    write_json(index_path, index)
    for p in out_paths:
        print(f"RENDER: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
