"""pdf_quality_report.py -- write parse_quality.json for an ingested PDF.

Scores every artifact layer produced so far and ALWAYS writes
<out-root>/<paper_id>/parse_quality.json, even for partial or failed
ingestions (that is the point: downstream consumers read this file FIRST
and never trust an artifact whose layer is not "ok").

The needs_visual_check[] list is the ONLY sanctioned trigger for having
Claude visually inspect a page/figure/table PNG -- plus items the human
explicitly designates as important.

Usage:
    py scripts/research/pdf_quality_report.py --pdf docs/papers/Foo_2020_JAR.pdf
    py scripts/research/pdf_quality_report.py --paper Foo_2020_JAR
        [--out-root outputs/ai/pdf]
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"

# A page whose markdown is shorter than this is treated as having no
# extractable text (likely scanned or image-only).
EMPTY_PAGE_CHARS = 20

# Markdown table separator row as emitted by pymupdf4llm (e.g. |---|---|).
MD_TABLE_SEP_RE = re.compile(r"(?m)^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")


def detect_inline_footnote_markers(page_texts):
    """Conservative inline-footnote detection for pages whose footnote layer
    came back empty. Fires only when BOTH a superscript marker <sup>N</sup>
    appears in the body AND a footnote-like line starting with the same N
    exists somewhere (layouts like FRL where the heuristic finds no footnote
    region and the footnote text stays inline). Returns the matching markers.
    """
    markers = set()
    line_starts = set()
    for text in page_texts:
        markers.update(re.findall(r"<sup>(\d{1,3})</sup>", text))
        for m in re.finditer(r"(?m)^(?:>\s*)?(\d{1,3})\s+\S", text):
            line_starts.add(m.group(1))
    return sorted(markers & line_starts, key=int)


def eprint(*args):
    print(*args, file=sys.stderr)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def count_jsonl(path: Path):
    if not path.is_file():
        return None
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="source PDF path (paper_id = file stem)")
    group.add_argument("--paper", help="paper_id (artifact dir name)")
    ap.add_argument("--out-root", default="outputs/ai/pdf")
    args = ap.parse_args()

    paper_id = args.paper if args.paper else Path(args.pdf).stem
    art_dir = Path(args.out_root) / paper_id
    quality_path = art_dir / "parse_quality.json"

    manifest = load_json(art_dir / "manifest.json")
    layers = {}
    needs_visual = []
    flags = []

    if manifest is None:
        # Even a missing/failed ingestion produces a parse_quality.json.
        quality = {
            "schema_version": SCHEMA_VERSION,
            "paper_id": paper_id,
            "source_sha256": None,
            "tools": {},
            "layers": {"text": {"status": "failed", "flags": ["no manifest.json; ingestion missing or crashed"]}},
            "overall": "failed",
            "needs_visual_check": [],
        }
        write_json(quality_path, quality)
        eprint(f"[quality] no manifest for {paper_id}; wrote failed report: {quality_path}")
        return 1

    # --- text layer ------------------------------------------------------------
    pages_dir = art_dir / "text" / "pages"
    page_files = sorted(pages_dir.glob("page-*.md")) if pages_dir.is_dir() else []
    empty_pages = []
    page_texts = []
    for pf in page_files:
        try:
            text = pf.read_text(encoding="utf-8")
        except OSError:
            empty_pages.append(pf.name)
            continue
        page_texts.append(text)
        if len(text.strip()) < EMPTY_PAGE_CHARS:
            empty_pages.append(pf.name)
    n_pages = len(page_files)
    text_flags = []
    if n_pages == 0:
        text_status = "failed"
        text_flags.append("no page markdown found")
    else:
        empty_ratio = len(empty_pages) / n_pages
        if empty_ratio == 0:
            text_status = "ok"
        elif empty_ratio < 0.5:
            text_status = "degraded"
            text_flags.append(f"{len(empty_pages)}/{n_pages} pages have no extractable text (scanned?)")
        else:
            text_status = "failed"
            text_flags.append(f"{len(empty_pages)}/{n_pages} pages empty; likely a scanned PDF (no OCR in v1)")
    for name in empty_pages:
        needs_visual.append({
            "artifact": f"text/pages/{name}",
            "reason": "no extractable text on this page (render and inspect visually)",
        })
    sections = load_json(art_dir / "text" / "sections.json") or {"sections": []}
    layers["text"] = {
        "status": text_status,
        "pages": n_pages,
        "empty_text_pages": len(empty_pages),
        "headings": len(sections.get("sections", [])),
        "grobid": manifest.get("tools", {}).get("grobid", "not_configured"),
        "flags": text_flags,
    }

    # --- footnotes layer ----------------------------------------------------------
    notes = count_jsonl(art_dir / "footnotes.jsonl")
    if notes is None:
        layers["footnotes"] = {"status": "not-run"}
    else:
        source = notes[0].get("source", "unknown") if notes else "none"
        fn_flags = []
        # GROBID being unavailable is a quality degradation, never a failure:
        # heuristic footnotes may MERGE adjacent footnotes into one block and
        # must be spot-checked against the PDF before quoting.
        if source == "heuristic":
            fn_flags.append("heuristic extraction (GROBID unavailable): adjacent footnotes "
                            "may be merged into one block; spot-check against the PDF before quoting")
            fn_status = "degraded"
        else:
            fn_status = "ok" if notes else "empty"
        if fn_status == "empty":
            # count=0 does NOT guarantee the paper has no footnotes: some
            # layouts (e.g. FRL) defeat the heuristic and footnote text stays
            # inline in the text layer (observed: Koga & Yamaguchi 2023 trial).
            inline = detect_inline_footnote_markers(page_texts)
            if inline:
                fn_status = "degraded"
                fn_flags.append(
                    "possible_inline_footnotes_in_text: no footnotes were extracted, but "
                    f"footnote-like marker(s) {', '.join(inline)} appear inline in the page "
                    "text; count=0 does not mean the paper has no footnotes -- verify via "
                    "page packets before citing")
        layers["footnotes"] = {
            "status": fn_status,
            "count": len(notes),
            "source": source,
            "flags": fn_flags,
        }

    # --- figures layer (P2) --------------------------------------------------------
    figs = load_json(art_dir / "figures" / "figures.json")
    if figs is None:
        layers["figures"] = {"status": "not-run"}
    else:
        entries = figs.get("figures", [])
        fig_flags = []
        fig_status = "ok" if entries else "empty"
        n_caption_only = sum(1 for e in entries if e.get("method") == "caption-only")
        n_raster_only = sum(1 for e in entries if e.get("method") == "raster-only")
        missing_png = [e.get("id") for e in entries
                       if not (art_dir / e.get("png", "")).is_file()]
        if n_caption_only:
            fig_status = "degraded"
            fig_flags.append(
                f"{n_caption_only} caption-only figure(s) (vector graphics, crop unknown; "
                "the PNG is a full-page render -- locate the figure visually before citing)")
        if n_raster_only:
            fig_flags.append(
                f"{n_raster_only} large uncaptioned image(s) kept as raster-only; "
                "may be decorative rather than a real figure")
        if missing_png:
            fig_status = "degraded"
            fig_flags.append(f"missing PNG for: {', '.join(str(x) for x in missing_png)}")
        layers["figures"] = {
            "status": fig_status,
            "count": len(entries),
            "flags": fig_flags,
        }

    # --- tables layer: extraction deferred (see SKILL / trial doc) ------------------
    if (art_dir / "tables" / "tables.json").exists():
        layers["tables"] = {"status": "extracted",
                            "flags": ["scored by pdf_extract_tables.py in a later phase"]}
    else:
        layers["tables"] = {"status": "not-run"}

    # --- references layer (P3, GROBID) ---------------------------------------------
    refs = count_jsonl(art_dir / "references" / "references.jsonl")
    if refs is None:
        layers["references"] = {"status": "not-run"}
    else:
        ref_flags = []
        n_unresolved = sum(1 for r in refs
                           if (r.get("resolved") or {}).get("status") == "unresolved")
        if not refs:
            ref_status = "degraded"
            ref_flags.append("0 references extracted from an academic paper -- "
                             "likely a GROBID failure; check the run log")
        else:
            ref_status = "ok"
            if n_unresolved:
                ref_flags.append(
                    f"{n_unresolved}/{len(refs)} unresolved (no verified DOI) -- do not "
                    "cite bibliographic details of unresolved entries without checking "
                    "their `raw` string; never guess-complete a reference")
        layers["references"] = {
            "status": ref_status,
            "count": len(refs),
            "unresolved": n_unresolved,
            "flags": ref_flags,
        }

    # --- citations layer (P3, GROBID) ----------------------------------------------
    cites = count_jsonl(art_dir / "citations" / "citation_contexts.jsonl")
    if cites is None:
        layers["citations"] = {"status": "not-run"}
    else:
        cit_flags = []
        n_unlinked = sum(1 for c in cites if not c.get("ref_id"))
        if not cites:
            cit_status = "degraded"
            cit_flags.append("0 in-text citations found -- likely a GROBID fulltext "
                             "failure; check the run log")
        else:
            cit_status = "ok"
            if n_unlinked:
                cit_flags.append(
                    f"{n_unlinked}/{len(cites)} context(s) not linked to the references "
                    "layer (ref_id null); rely on their inline ref_desc instead")
            ref_count = layers.get("references", {}).get("count") or 0
            if len(cites) < ref_count:
                cit_status = "degraded"
                cit_flags.append(
                    f"only {len(cites)} context(s) vs {ref_count} references -- GROBID's "
                    "in-text marker recall is limited on this layout; treat contexts as a "
                    "SAMPLE and never infer that a work is NOT cited from this layer")
        layers["citations"] = {
            "status": cit_status,
            "count": len(cites),
            "unlinked": n_unlinked,
            "flags": cit_flags,
        }

    if (layers["tables"]["status"] == "not-run"
            and any(MD_TABLE_SEP_RE.search(t) for t in page_texts)):
        layers["tables"]["flags"] = [
            "markdown_table_blocks_present_unverified: markdown table-like blocks are "
            "visible in the text layer but the tables layer has not been extracted or "
            "verified; table values seen in text packets are UNVERIFIED -- cite a cell "
            "only after visually matching it against a page PNG from pdf_render_page.py"]

    # --- overall -----------------------------------------------------------------
    statuses = [v["status"] for v in layers.values() if v["status"] not in ("not-run", "extracted")]
    if "failed" in statuses:
        overall = "failed"
    elif "degraded" in statuses or any(v.get("flags") for v in layers.values() if isinstance(v, dict)):
        overall = "degraded" if "degraded" in statuses else "ok"
    else:
        overall = "ok"

    quality = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_sha256": manifest.get("source_sha256"),
        "tools": manifest.get("tools", {}),
        "layers": layers,
        "overall": overall,
        "needs_visual_check": needs_visual,
        "notes": flags,
    }
    write_json(quality_path, quality)
    print(f"[quality] overall={overall} text={text_status} "
          f"footnotes={layers['footnotes'].get('count', 'n/a')} "
          f"visual_checks={len(needs_visual)}")
    print(f"[quality] report: {quality_path}")
    return 0 if overall != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
