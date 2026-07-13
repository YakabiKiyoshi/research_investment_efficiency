"""pdf_ingest.py -- text-layer ingestion of a scholarly PDF into layered artifacts.

Creates under <out-root>/<paper_id>/ (paper_id = PDF file stem):
    manifest.json            run manifest (sha256, tool versions, layer status)
    text/full.md             layout-aware markdown (PyMuPDF4LLM)
    text/pages/page-NNNN.md  per-page markdown (query-packet building unit)
    text/sections.json       heading tree with page numbers
    text/tei.xml             GROBID TEI (only if a GROBID service is reachable)
    footnotes.jsonl          footnotes kept OUT of the body text

Design rules:
- Deterministic extraction only; no LLM involved.
- All JSON/JSONL/MD written as BOM-free UTF-8 (never route through
  PowerShell Out-File, which would add a BOM).
- GROBID is optional: unreachable service degrades gracefully and is
  recorded in the manifest; it never fails the run.
- Idempotent: if manifest sha256 matches the source PDF, the run is skipped
  unless --force.
- Progress goes to stdout; errors to stderr with a non-zero exit code.

Usage:
    py scripts/research/pdf_ingest.py --pdf docs/papers/Foo_2020_JAR.pdf
        [--out-root outputs/ai/pdf] [--grobid-url http://localhost:8070]
        [--force]
"""

import argparse
import datetime
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"


def eprint(*args):
    print(*args, file=sys.stderr)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def extract_sections(page_texts):
    """Heading tree from markdown headings, with 1-based page numbers."""
    sections = []
    for pageno, text in enumerate(page_texts, start=1):
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if m:
                sections.append({
                    "level": len(m.group(1)),
                    "title": m.group(2),
                    "page": pageno,
                })
    return sections


def extract_footnotes_heuristic(doc):
    """Bottom-of-page small-font blocks with a leading footnote marker.

    Heuristic (flagged as such downstream): a block whose top edge lies in
    the bottom 25% of the page, whose median span size is at least 1pt below
    the page's body median, and whose text starts with a 1-3 digit marker
    (or an asterisk/dagger). Confidence is a property of the method, not of
    individual entries.
    """
    notes = []
    for pageno in range(len(doc)):
        page = doc[pageno]
        d = page.get_text("dict")
        spans = [s for b in d.get("blocks", []) if b.get("type") == 0
                 for l in b.get("lines", []) for s in l.get("spans", [])]
        sizes = [s["size"] for s in spans if s.get("text", "").strip()]
        if not sizes:
            continue
        body_size = statistics.median(sizes)
        page_h = page.rect.height
        for b in d.get("blocks", []):
            if b.get("type") != 0:
                continue
            y0 = b["bbox"][1]
            if y0 < page_h * 0.75:
                continue
            btext = " ".join(
                s.get("text", "") for l in b.get("lines", []) for s in l.get("spans", [])
            ).strip()
            bsizes = [s["size"] for l in b.get("lines", []) for s in l.get("spans", [])
                      if s.get("text", "").strip()]
            if not btext or not bsizes:
                continue
            if statistics.median(bsizes) > body_size - 1.0:
                continue
            m = re.match(r"^(\d{1,3}|[*†‡])\s*(.+)$", btext)
            if not m:
                continue
            notes.append({
                "id": f"fn-{len(notes) + 1:03d}",
                "marker": m.group(1),
                "page": pageno + 1,
                "text": m.group(2).strip(),
                "source": "heuristic",
            })
    return notes


def extract_footnotes_tei(tei_xml: str):
    """Footnotes from GROBID TEI (<note place="foot">). Preferred source."""
    import xml.etree.ElementTree as ET
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        eprint(f"[ingest] TEI parse error, keeping heuristic footnotes: {exc}")
        return None
    notes = []
    for i, note in enumerate(root.iterfind(".//tei:note[@place='foot']", ns), start=1):
        text = " ".join("".join(note.itertext()).split())
        if not text:
            continue
        notes.append({
            "id": f"fn-{i:03d}",
            "marker": note.get("n", ""),
            "page": None,  # TEI carries no page unless coordinates are enabled
            "text": text,
            "source": "grobid",
        })
    return notes


def try_grobid(pdf_path: Path, grobid_url: str, timeout_connect: float = 3.0):
    """POST the PDF to a local GROBID service. Returns TEI XML or None."""
    try:
        import requests
    except ImportError:
        eprint("[ingest] requests not installed; skipping GROBID.")
        return None
    url = grobid_url.rstrip("/") + "/api/processFulltextDocument"
    try:
        with pdf_path.open("rb") as f:
            resp = requests.post(url, files={"input": f},
                                 timeout=(timeout_connect, 300))
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
        eprint(f"[ingest] GROBID returned HTTP {resp.status_code}; skipping.")
        return None
    except Exception as exc:  # connection refused, timeout, ...
        eprint(f"[ingest] GROBID unavailable ({exc.__class__.__name__}); "
               "continuing without it.")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True, help="path to the source PDF")
    ap.add_argument("--out-root", default="outputs/ai/pdf",
                    help="artifact store root (default: outputs/ai/pdf)")
    ap.add_argument("--grobid-url", default=None,
                    help="GROBID base URL (default: env GROBID_URL, else skip)")
    ap.add_argument("--force", action="store_true",
                    help="re-ingest even if the source hash is unchanged")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        eprint(f"[ingest] PDF not found: {pdf_path}")
        return 2
    if pdf_path.suffix.lower() != ".pdf":
        eprint(f"[ingest] not a .pdf file: {pdf_path}")
        return 2

    paper_id = pdf_path.stem
    art_dir = Path(args.out_root) / paper_id
    manifest_path = art_dir / "manifest.json"
    src_hash = sha256_of(pdf_path)

    if manifest_path.is_file() and not args.force:
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old.get("source_sha256") == src_hash:
                print(f"[ingest] unchanged (sha256 match), skipping: {paper_id}")
                print(f"[ingest] artifacts: {art_dir}")
                return 0
        except (json.JSONDecodeError, OSError):
            pass  # unreadable manifest -> re-ingest

    try:
        import fitz  # PyMuPDF
        import pymupdf4llm
    except ImportError as exc:
        eprint(f"[ingest] missing dependency: {exc}. "
               "Install with: py -m pip install pymupdf pymupdf4llm")
        return 3

    print(f"[ingest] paper_id={paper_id}")
    print(f"[ingest] source={pdf_path} sha256={src_hash[:12]}...")

    # --- text layer (PyMuPDF4LLM, page chunks) --------------------------------
    chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    page_texts = [c.get("text", "") for c in chunks]
    write_text(art_dir / "text" / "full.md", "\n\n".join(page_texts))
    for i, text in enumerate(page_texts, start=1):
        write_text(art_dir / "text" / "pages" / f"page-{i:04d}.md", text)
    sections = extract_sections(page_texts)
    write_json(art_dir / "text" / "sections.json",
               {"schema_version": SCHEMA_VERSION, "sections": sections})
    print(f"[ingest] text: {len(page_texts)} pages, {len(sections)} headings")

    # --- GROBID (optional) ------------------------------------------------------
    import os
    grobid_url = args.grobid_url or os.environ.get("GROBID_URL", "")
    grobid_status = "not_configured"
    tei_xml = None
    if grobid_url:
        tei_xml = try_grobid(pdf_path, grobid_url)
        grobid_status = "ok" if tei_xml else "unavailable"
        if tei_xml:
            write_text(art_dir / "text" / "tei.xml", tei_xml)
            print("[ingest] GROBID TEI saved")

    # --- footnotes (TEI preferred, heuristic fallback) ---------------------------
    doc = fitz.open(str(pdf_path))
    footnotes = None
    if tei_xml:
        footnotes = extract_footnotes_tei(tei_xml)
    if footnotes is None or len(footnotes) == 0:
        footnotes = extract_footnotes_heuristic(doc)
    fn_path = art_dir / "footnotes.jsonl"
    fn_path.parent.mkdir(parents=True, exist_ok=True)
    with fn_path.open("w", encoding="utf-8", newline="\n") as f:
        for note in footnotes:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
    fn_source = footnotes[0]["source"] if footnotes else "none"
    print(f"[ingest] footnotes: {len(footnotes)} (source: {fn_source})")

    # --- manifest ------------------------------------------------------------------
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_pdf": str(pdf_path).replace("\\", "/"),
        "source_sha256": src_hash,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "tools": {
            "pymupdf": fitz.__doc__.split()[1] if fitz.__doc__ else "unknown",
            "pymupdf4llm": getattr(pymupdf4llm, "__version__", "unknown"),
            "grobid": grobid_status,
        },
        "pages": len(page_texts),
        "layers": {
            "text": "ok",
            "footnotes": f"ok ({fn_source})" if footnotes else "empty",
            "figures": "not-run",     # P2: pdf_extract_figures.py
            "tables": "not-run",      # P2: pdf_extract_tables.py
            "references": "not-run",  # P3: pdf_extract_references.py
            "citations": "not-run",   # P3: pdf_build_citation_contexts.py
        },
    }
    write_json(manifest_path, manifest)
    doc.close()
    print(f"[ingest] done: {art_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
