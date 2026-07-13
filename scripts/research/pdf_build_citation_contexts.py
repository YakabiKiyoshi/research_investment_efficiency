"""pdf_build_citation_contexts.py -- P3 citations layer via GROBID.

Sends the source PDF to GROBID (/api/processFulltextDocument) and extracts
every in-text citation marker (<ref type="bibr">) with its surrounding
context window and section heading. Writes
<out-root>/<paper_id>/citations/citation_contexts.jsonl -- one JSON object
per in-text citation:

    {"id": "cite-0001", "ref_tei_id": "b12", "ref_id": "ref-013" | null,
     "marker": "Ball and Brown (1968)", "section": "1. Introduction",
     "context": "...text around the marker...", "source": "grobid"}

ref_id links into references/references.jsonl (pdf_extract_references.py)
by GROBID's TEI id; when that layer is absent or the id is unknown, ref_id
is null and the entry still carries the reference description from the
fulltext TEI itself (ref_desc). GROBID is REQUIRED (exit 4 when
unreachable); start it with:
    docker run --rm -d -p 8070:8070 lfoppiano/grobid:0.8.1

Usage:
    py scripts/research/pdf_build_citation_contexts.py --paper Foo_2020_JAR
        [--out-root outputs/ai/pdf] [--grobid-url http://localhost:8070]
        [--window 240]

Prints "CITATIONS: <path>" as the last stdout line.
Exit codes: 0 ok, 1 sha256 mismatch, 2 bad args/missing artifacts,
4 GROBID unreachable/failed.
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

from pdf_extract_references import (DEFAULT_GROBID, TEI_NS, eprint,
                                    grobid_alive, grobid_post_pdf, load_json,
                                    parse_bibl, sha256_of, text_of)

SCHEMA_VERSION = "1.0"


def para_with_markers(p_el):
    """Paragraph text plus (char_offset, marker_text, target) per bibr ref."""
    parts = []
    markers = []

    def walk(el):
        if el.tag == f"{{{TEI_NS['tei']}}}ref" and el.get("type") == "bibr":
            marker_text = "".join(el.itertext())
            markers.append((sum(len(s) for s in parts),
                            " ".join(marker_text.split()),
                            (el.get("target") or "").lstrip("#")))
            parts.append(marker_text)
        else:
            if el.text:
                parts.append(el.text)
            for child in el:
                walk(child)
        if el.tail:
            parts.append(el.tail)

    if p_el.text:
        parts.append(p_el.text)
    for child in p_el:
        walk(child)
    return "".join(parts), markers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="source PDF path (paper_id = file stem)")
    group.add_argument("--paper", help="paper_id (artifact dir name)")
    ap.add_argument("--out-root", default="outputs/ai/pdf")
    ap.add_argument("--grobid-url", default=os.environ.get("GROBID_URL", DEFAULT_GROBID))
    ap.add_argument("--window", type=int, default=240,
                    help="context chars kept on each side of a marker (default 240)")
    args = ap.parse_args()

    paper_id = args.paper if args.paper else Path(args.pdf).stem
    art_dir = Path(args.out_root) / paper_id
    manifest = load_json(art_dir / "manifest.json")
    if manifest is None:
        eprint(f"[citations] no manifest.json for '{paper_id}'; run pdf_ingest.py first")
        return 2

    pdf_path = Path(args.pdf) if args.pdf else Path(manifest.get("source_pdf", ""))
    if not pdf_path.is_file():
        eprint(f"[citations] source PDF not found: {pdf_path}")
        return 2
    actual_sha = sha256_of(pdf_path)
    expected_sha = manifest.get("source_sha256")
    if expected_sha and actual_sha != expected_sha:
        eprint("[citations] sha256 mismatch vs manifest; re-run pdf_ingest.py")
        return 1

    base = args.grobid_url.rstrip("/")
    if not grobid_alive(base):
        eprint(f"[citations] GROBID unreachable at {base} -- start it with:\n"
               "  docker run --rm -d -p 8070:8070 lfoppiano/grobid:0.8.1\n"
               "then set GROBID_URL or pass --grobid-url. The citations layer "
               "stays not-run until then.")
        return 4

    try:
        tei = grobid_post_pdf(base, "/api/processFulltextDocument", pdf_path)
        root = ET.fromstring(tei)
    except (urllib.error.URLError, OSError, ET.ParseError) as exc:
        eprint(f"[citations] GROBID processFulltextDocument failed: {exc}")
        return 4

    # Reference descriptions from THIS TEI (self-contained provenance).
    xml_id = "{http://www.w3.org/XML/1998/namespace}id"
    tei_refs = {}
    for i, bibl in enumerate(root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)):
        entry = parse_bibl(bibl, i + 1)
        if bibl.get(xml_id):
            tei_refs[bibl.get(xml_id)] = entry

    # Link into the references layer when available (matched by TEI id).
    ref_layer = {}
    ref_path = art_dir / "references" / "references.jsonl"
    if ref_path.is_file():
        for line in ref_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("tei_id"):
                    ref_layer[row["tei_id"]] = row["id"]

    parent = {child: par for par in root.iter() for child in par}

    def section_of(el):
        cur = el
        while cur in parent:
            cur = parent[cur]
            if cur.tag == f"{{{TEI_NS['tei']}}}div":
                head = text_of(cur.find("tei:head", TEI_NS))
                if head:
                    return head
        return ""

    contexts = []
    n_footnote_markers = 0
    body = root.find(".//tei:body", TEI_NS)
    for p in (body.findall(".//tei:p", TEI_NS) if body is not None else []):
        text, markers = para_with_markers(p)
        flat = " ".join(text.split())
        section = section_of(p)
        for off, marker, target in markers:
            # A targetless, purely numeric "citation" is a footnote
            # superscript that GROBID misclassified as bibr -- skip it.
            if not target and not re.search(r"[A-Za-z]", marker):
                n_footnote_markers += 1
                continue
            # Recompute the offset in the whitespace-flattened text.
            probe = " ".join(text[:off].split())
            lo = max(0, len(probe) - args.window)
            hi = min(len(flat), len(probe) + len(marker) + args.window)
            snippet = ("..." if lo > 0 else "") + flat[lo:hi] + \
                      ("..." if hi < len(flat) else "")
            desc = tei_refs.get(target)
            contexts.append({
                "id": f"cite-{len(contexts) + 1:04d}",
                "ref_tei_id": target or None,
                "ref_id": ref_layer.get(target),
                "ref_desc": (f"{'; '.join(desc['authors'][:3])} "
                             f"({desc['year']}) {desc['title']}".strip()
                             if desc else None),
                "marker": marker,
                "section": section,
                "context": snippet,
                "source": "grobid",
            })

    cit_dir = art_dir / "citations"
    cit_dir.mkdir(parents=True, exist_ok=True)
    out_path = cit_dir / "citation_contexts.jsonl"
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for c in contexts:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_sha256": expected_sha or actual_sha,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "grobid_url": base,
        "count": len(contexts),
        "unlinked": sum(1 for c in contexts if c["ref_id"] is None),
        "skipped_footnote_markers": n_footnote_markers,
        "tei_bibliography_size": len(tei_refs),
    }
    (cit_dir / "citations_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[citations] {len(contexts)} in-text citation(s); "
          f"unlinked={meta['unlinked']} (no matching references-layer id)")
    print(f"CITATIONS: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
