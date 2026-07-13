"""pdf_extract_figures.py -- P2 figures layer: caption-anchored extraction.

Deterministic, PyMuPDF-only. Detects figures by their caption lines
("Figure N" / "Fig. N" / "FIGURE N" at block start) and pairs each caption
with the nearest raster image above it on the same page:

  caption+raster  caption paired with a raster image -> cropped PNG
  caption-only    vector-drawn figure (no raster to crop) -> full-page PNG;
                  scored degraded so the consumer knows the crop is unknown
  raster-only     large uncaptioned image (>= RASTER_ONLY_MIN_PT both dims);
                  small ones (publisher logos etc.) are ignored

The 2026-07 feasibility probe on 4 real finance/accounting PDFs found every
true figure had a caption + same-page raster image, while caption-less
rasters were publisher logos -- hence caption-first detection.

Writes <out-root>/<paper_id>/figures/figures.json plus fig-NNN.png crops.
The source PDF's sha256 is re-verified against manifest.json first.

Usage:
    py scripts/research/pdf_extract_figures.py --paper Foo_2020_JAR
    py scripts/research/pdf_extract_figures.py --pdf docs/papers/Foo_2020_JAR.pdf
        [--out-root outputs/ai/pdf] [--dpi 200]

Prints "FIGURES: <path to figures.json>" as the last stdout line.
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

CAPTION_RE = re.compile(r"^\s*(FIGURE|Figure|Fig\.?)\s+(\d+[A-Za-z]?)\s*[.:]?\s*(.*)",
                        re.DOTALL)

# Minimum width/height (pt) for a raster image to be considered at all
# (anything smaller is a logo/ornament even if a caption sits nearby).
RASTER_MIN_PT = 40
# Uncaptioned rasters must be large to be kept as raster-only.
RASTER_ONLY_MIN_PT = 120
# Pad (pt) added around a paired image bbox when cropping.
CROP_PAD_PT = 6
# A paired image must end no more than this many pt below the caption top
# (captions sit under their figure).
PAIR_TOLERANCE_PT = 10


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


def page_figures(page, fitz):
    """(captions, images) on one page. captions: dicts; images: fitz.Rect."""
    captions = []
    for b in page.get_text("blocks"):
        if b[6] != 0:
            continue
        m = CAPTION_RE.match(b[4])
        if m:
            captions.append({
                "bbox": fitz.Rect(b[:4]),
                "label": f"{m.group(1).rstrip('.')} {m.group(2)}",
                "number": m.group(2),
                "caption": " ".join(b[4].split())[:300],
            })
    images = []
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.width >= RASTER_MIN_PT and r.height >= RASTER_MIN_PT:
            images.append(r)
    return captions, images


def pair(captions, images):
    """Assign each caption the nearest raster image ending above it
    (with x-overlap). Returns list of (caption, image|None) plus leftover
    images."""
    pool = list(images)
    out = []
    for cap in sorted(captions, key=lambda c: (c["bbox"].y0, c["bbox"].x0)):
        best, best_gap = None, None
        for img in pool:
            if img.x1 <= cap["bbox"].x0 or img.x0 >= cap["bbox"].x1:
                continue  # no horizontal overlap
            gap = cap["bbox"].y0 - img.y1
            if gap < -PAIR_TOLERANCE_PT:
                continue  # image not above the caption
            if best_gap is None or gap < best_gap:
                best, best_gap = img, gap
        if best is not None:
            pool.remove(best)
        out.append((cap, best))
    return out, pool


def main() -> int:
    try:
        import fitz
    except ImportError:
        eprint("[figures] missing dependency: pymupdf -- run: py -m pip install pymupdf")
        return 3

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="source PDF path (paper_id = file stem)")
    group.add_argument("--paper", help="paper_id (artifact dir name)")
    ap.add_argument("--out-root", default="outputs/ai/pdf")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    paper_id = args.paper if args.paper else Path(args.pdf).stem
    art_dir = Path(args.out_root) / paper_id
    manifest = load_json(art_dir / "manifest.json")
    if manifest is None:
        eprint(f"[figures] no manifest.json for '{paper_id}' under {args.out_root}; "
               "run pdf_ingest.py first")
        return 2

    pdf_path = Path(args.pdf) if args.pdf else Path(manifest.get("source_pdf", ""))
    if not pdf_path.is_file():
        eprint(f"[figures] source PDF not found: {pdf_path}")
        return 2
    actual_sha = sha256_of(pdf_path)
    expected_sha = manifest.get("source_sha256")
    if expected_sha and actual_sha != expected_sha:
        eprint(f"[figures] sha256 mismatch: PDF {actual_sha[:12]}... vs manifest "
               f"{str(expected_sha)[:12]}...; artifacts are stale -- re-run pdf_ingest.py")
        return 1

    fig_dir = art_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    entries = []
    for pno in range(doc.page_count):
        page = doc[pno]
        captions, images = page_figures(page, fitz)
        paired, leftover = pair(captions, images)
        for cap, img in paired:
            entries.append({"page": pno + 1, "label": cap["label"],
                            "number": cap["number"], "caption": cap["caption"],
                            "method": "caption+raster" if img else "caption-only",
                            "bbox": [round(v, 1) for v in img] if img else None,
                            "_clip": img})
        for img in leftover:
            if img.width >= RASTER_ONLY_MIN_PT and img.height >= RASTER_ONLY_MIN_PT:
                entries.append({"page": pno + 1, "label": None, "number": None,
                                "caption": None, "method": "raster-only",
                                "bbox": [round(v, 1) for v in img], "_clip": img})

    for i, e in enumerate(entries, start=1):
        e["id"] = f"fig-{i:03d}"
        page = doc[e["page"] - 1]
        clip = e.pop("_clip")
        if clip is not None:
            clip = fitz.Rect(clip.x0 - CROP_PAD_PT, clip.y0 - CROP_PAD_PT,
                             clip.x1 + CROP_PAD_PT, clip.y1 + CROP_PAD_PT) & page.rect
        pix = page.get_pixmap(dpi=args.dpi, clip=clip)  # clip=None -> full page
        png_name = f"{e['id']}.png"
        pix.save(str(fig_dir / png_name))
        e["png"] = f"figures/{png_name}"
        e["dpi"] = args.dpi
        e["crop"] = "bbox" if clip is not None else "full-page"
        print(f"[figures] {e['id']} p.{e['page']} {e['method']}: "
              f"{e['label'] or '(uncaptioned)'} -> {e['png']}")
    doc.close()

    index = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_sha256": expected_sha or actual_sha,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "figures": [{k: v for k, v in e.items()} for e in entries],
    }
    index_path = fig_dir / "figures.json"
    write_json(index_path, index)
    print(f"[figures] {len(entries)} figure(s) extracted")
    print(f"FIGURES: {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
