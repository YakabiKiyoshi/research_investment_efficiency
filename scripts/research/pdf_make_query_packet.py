"""pdf_make_query_packet.py -- assemble a minimal, budgeted packet for Claude.

This is the ONLY sanctioned way for Claude to consume an ingested PDF:
never read text/full.md (or the PDF itself) into the main context. The
packet contains just the fragment that answers the ask, plus a mandatory
provenance header (paper_id, source_pdf, source_sha256, parse_quality
warnings, budget) and an explicit TRUNCATED marker when the budget cuts
the content.

Asks supported in P1 (text layers):
    quality              parse_quality.json, pretty-printed
    toc                  section tree (title/level/page)
    abstract             text from the document start (through the abstract)
    section:<query>      pages of the first section whose title matches
                         <query> (case-insensitive substring)
    page:<n> | <n>-<m>   specific page range of markdown
    footnote:<id|all>    one footnote (fn-003) or all footnotes
    figure:<id|n|all>    figure index entries (id, page, caption, PNG path);
                         requires pdf_extract_figures.py to have run
    reference:<id|all>   bibliography entries (authors/year/title/DOI/status);
                         requires pdf_extract_references.py (GROBID)
    citation:<id|all>    in-text citation contexts (cite-NNNN, or a ref-NNN id
                         to get every context citing that reference);
                         requires pdf_build_citation_contexts.py (GROBID)

Usage:
    py scripts/research/pdf_make_query_packet.py --paper Foo_2020_JAR --ask section:results
    py scripts/research/pdf_make_query_packet.py --pdf docs/papers/Foo_2020_JAR.pdf --ask quality
        [--out-root outputs/ai/pdf] [--budget 15000]

Prints the packet path as the last stdout line: "PACKET: <path>".
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"

# Markdown table separator row as emitted by pymupdf4llm (e.g. |---|---|).
MD_TABLE_SEP_RE = re.compile(r"(?m)^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")

UNVERIFIED_TABLE_WARNING = (
    "tables: table values visible in this packet are UNVERIFIED (tables layer "
    "not-run); before quoting any cell, render the page "
    "(py scripts/research/pdf_render_page.py --paper <id> --page <n>) and "
    "visually match the value against the PNG")


def eprint(*args):
    print(*args, file=sys.stderr)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_pages(art_dir: Path):
    pages_dir = art_dir / "text" / "pages"
    out = {}
    for pf in sorted(pages_dir.glob("page-*.md")):
        m = re.match(r"page-(\d+)\.md", pf.name)
        if m:
            out[int(m.group(1))] = pf.read_text(encoding="utf-8")
    return out


def quality_warnings(art_dir: Path):
    """(overall, [warning strings]) from parse_quality.json for the header."""
    q = load_json(art_dir / "parse_quality.json")
    if q is None:
        return ("MISSING", ["parse_quality.json not found -- run pdf_quality_report.py "
                            "before trusting any layer"])
    warnings = []
    for name, layer in q.get("layers", {}).items():
        if not isinstance(layer, dict):
            continue
        status = layer.get("status", "?")
        if status in ("degraded", "failed"):
            warnings.append(f"{name}: {status}")
        for flag in layer.get("flags", []) or []:
            warnings.append(f"{name}: {flag}")
    if q.get("needs_visual_check"):
        warnings.append(f"{len(q['needs_visual_check'])} item(s) need visual check")
    return (q.get("overall", "?"), warnings)


def build_body(art_dir: Path, ask: str):
    """Returns (title, untruncated body, provenance_paths, truncation_hint).

    Budget handling happens centrally in main(); branches only supply an
    ask-specific hint for the TRUNCATED marker. Raises ValueError on a bad
    or unsupported ask.
    """
    if ask == "quality":
        q = load_json(art_dir / "parse_quality.json")
        if q is None:
            raise ValueError("parse_quality.json not found; run pdf_quality_report.py first")
        return ("parse quality report",
                "```json\n" + json.dumps(q, ensure_ascii=False, indent=2) + "\n```",
                ["parse_quality.json"], "re-issue with a larger --budget")

    if ask == "toc":
        s = load_json(art_dir / "text" / "sections.json")
        if s is None:
            raise ValueError("text/sections.json not found; run pdf_ingest.py first")
        lines = [f"{'  ' * (sec['level'] - 1)}- {sec['title']} (p.{sec['page']})"
                 for sec in s.get("sections", [])]
        return ("table of contents", "\n".join(lines) or "(no headings detected)",
                ["text/sections.json"], "re-issue with a larger --budget")

    if ask == "abstract":
        pages = load_pages(art_dir)
        if not pages:
            raise ValueError("no page markdown; run pdf_ingest.py first")
        head = "\n\n".join(pages[n] for n in sorted(pages)[:2])
        # Cut at the heading that follows an "Abstract" marker, if present.
        m = re.search(r"(?is)abstract\b(.{200,}?)(?:\n#{1,6}\s|\Z)", head)
        body = m.group(0) if m else head
        return ("abstract / opening", body, ["text/pages/page-0001.md"],
                "ask page:1-2 for the full opening")

    m = re.match(r"^section:(.+)$", ask)
    if m:
        query = m.group(1).strip().lower()
        s = load_json(art_dir / "text" / "sections.json")
        if s is None:
            raise ValueError("text/sections.json not found; run pdf_ingest.py first")
        secs = s.get("sections", [])
        hit = next((i for i, sec in enumerate(secs) if query in sec["title"].lower()), None)
        if hit is None:
            titles = "; ".join(sec["title"] for sec in secs[:30])
            raise ValueError(f"no section title matches '{query}'. Known: {titles}")
        start = secs[hit]["page"]
        end = secs[hit + 1]["page"] if hit + 1 < len(secs) else None
        pages = load_pages(art_dir)
        page_nums = [n for n in sorted(pages) if n >= start and (end is None or n <= end)]
        body = "\n\n".join(pages[n] for n in page_nums)
        return (f"section '{secs[hit]['title']}' (pages {start}-{end or 'end'})",
                body, [f"text/pages/page-{n:04d}.md" for n in page_nums],
                f"section spans pages {start}-{end or max(pages)}; ask page:<n> for the rest")

    m = re.match(r"^page:(\d+)(?:-(\d+))?$", ask)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        pages = load_pages(art_dir)
        nums = [n for n in sorted(pages) if lo <= n <= hi]
        if not nums:
            raise ValueError(f"pages {lo}-{hi} not found (document has {len(pages)} pages)")
        body = "\n\n".join(f"<!-- page {n} -->\n{pages[n]}" for n in nums)
        return (f"pages {lo}-{hi}", body,
                [f"text/pages/page-{n:04d}.md" for n in nums],
                "narrow the page range")

    m = re.match(r"^figure:(.+)$", ask)
    if m:
        want = m.group(1).strip().lower()
        figs = load_json(art_dir / "figures" / "figures.json")
        if figs is None:
            raise ValueError("figures not extracted; run pdf_extract_figures.py first")
        entries = figs.get("figures", [])
        total = len(entries)
        if want != "all":
            entries = [e for e in entries
                       if e.get("id") == want or str(e.get("number", "")).lower() == want]
            if not entries:
                raise ValueError(f"figure '{want}' not found ({total} entries exist)")
        lines = []
        for e in entries:
            lines.append(
                f"- **{e['id']}** (p.{e['page']}, method: {e['method']}, crop: {e.get('crop')}): "
                f"{e.get('caption') or '(no caption)'}\n"
                f"  PNG: {e.get('png')} (visual inspection of this file is sanctioned)")
        return (f"figures ({want})",
                "\n".join(lines) or "(no figures extracted)",
                ["figures/figures.json"], "ask a single figure id")

    m = re.match(r"^footnote:(.+)$", ask)
    if m:
        want = m.group(1).strip()
        fn_path = art_dir / "footnotes.jsonl"
        if not fn_path.is_file():
            raise ValueError("footnotes.jsonl not found; run pdf_ingest.py first")
        notes = [json.loads(line) for line in fn_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        total = len(notes)
        if want != "all":
            notes = [n for n in notes if n.get("id") == want or n.get("marker") == want]
            if not notes:
                raise ValueError(f"footnote '{want}' not found ({total} entries exist)")
        lines = [f"- **{n['id']}** (marker {n.get('marker', '?')}, p.{n.get('page', '?')}, "
                 f"source: {n.get('source', '?')}): {n['text']}" for n in notes]
        return (f"footnotes ({want})", "\n".join(lines), ["footnotes.jsonl"],
                "ask a single footnote id")

    m = re.match(r"^reference:(.+)$", ask)
    if m:
        want = m.group(1).strip().lower()
        ref_path = art_dir / "references" / "references.jsonl"
        if not ref_path.is_file():
            raise ValueError("references not extracted; run pdf_extract_references.py "
                             "first (requires GROBID)")
        refs = [json.loads(line) for line in ref_path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        total = len(refs)
        if want != "all":
            refs = [r for r in refs if r.get("id") == want]
            if not refs:
                raise ValueError(f"reference '{want}' not found ({total} entries exist)")
        lines = []
        for r in refs:
            status = r.get("resolved", {}).get("status", "?")
            bits = [f"- **{r['id']}** [{status}]",
                    "; ".join(r.get("authors", [])[:6]) or "(no authors parsed)",
                    f"({r.get('year') or '?'})", r.get("title") or "(no title parsed)"]
            if r.get("venue"):
                bits.append(f"_{r['venue']}_")
            if r.get("doi"):
                bits.append(f"DOI: {r['doi']}")
            lines.append(" ".join(bits))
        return (f"references ({want})", "\n".join(lines), ["references/references.jsonl"],
                "ask a single reference id")

    m = re.match(r"^citation:(.+)$", ask)
    if m:
        want = m.group(1).strip().lower()
        cit_path = art_dir / "citations" / "citation_contexts.jsonl"
        if not cit_path.is_file():
            raise ValueError("citation contexts not extracted; run "
                             "pdf_build_citation_contexts.py first (requires GROBID)")
        cites = [json.loads(line) for line in cit_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        total = len(cites)
        if want != "all":
            cites = [c for c in cites
                     if c.get("id") == want or (c.get("ref_id") or "").lower() == want]
            if not cites:
                raise ValueError(f"citation '{want}' not found (use cite-NNNN or a "
                                 f"ref-NNN id; {total} contexts exist)")
        lines = []
        for c in cites:
            ref = c.get("ref_id") or c.get("ref_desc") or c.get("ref_tei_id") or "?"
            lines.append(f"- **{c['id']}** (-> {ref}; section: {c.get('section') or '?'}; "
                         f"marker: {c.get('marker')})\n  {c.get('context')}")
        return (f"citation contexts ({want})", "\n".join(lines),
                ["citations/citation_contexts.jsonl"],
                "ask citation:<ref-id> to narrow to one reference")

    raise ValueError(
        f"unknown ask '{ask}'. Supported: quality | toc | abstract | "
        "section:<query> | page:<n>[-<m>] | footnote:<id|all> | figure:<id|n|all> | "
        "reference:<id|all> | citation:<cite-id|ref-id|all>")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="source PDF path (paper_id = file stem)")
    group.add_argument("--paper", help="paper_id (artifact dir name)")
    ap.add_argument("--ask", required=True)
    ap.add_argument("--out-root", default="outputs/ai/pdf")
    ap.add_argument("--budget", type=int, default=15000,
                    help="max characters of content in the packet (default 15000)")
    args = ap.parse_args()

    paper_id = args.paper if args.paper else Path(args.pdf).stem
    art_dir = Path(args.out_root) / paper_id
    if not art_dir.is_dir():
        eprint(f"[packet] no artifacts for '{paper_id}' under {args.out_root}; "
               "run pdf_ingest.py first")
        return 2

    try:
        title, body, provenance, trunc_hint = build_body(art_dir, args.ask)
    except ValueError as exc:
        eprint(f"[packet] {exc}")
        return 2

    # Central budget enforcement: every ask gets the same TRUNCATED contract.
    full_len = len(body)
    truncated = full_len > args.budget
    if truncated:
        body = body[:args.budget] + (
            f"\n\n[TRUNCATED at budget {args.budget} chars "
            f"(full content: {full_len} chars); {trunc_hint}]")

    packets_dir = art_dir / "query-packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    existing = [int(m.group(1)) for p in packets_dir.iterdir()
                if (m := re.match(r"^(\d{4})$", p.name))]
    n = (max(existing) + 1) if existing else 1
    packet_dir = packets_dir / f"{n:04d}"
    packet_path = packet_dir / "packet.md"

    manifest = load_json(art_dir / "manifest.json") or {}
    overall, warnings = quality_warnings(art_dir)
    # If the delivered content contains markdown table-like text while the
    # tables layer is unextracted, say so explicitly: those numbers came from
    # the raw pymupdf4llm text pass and must not be quoted as evidence.
    if MD_TABLE_SEP_RE.search(body):
        q = load_json(art_dir / "parse_quality.json") or {}
        tables_status = (q.get("layers", {}).get("tables") or {}).get("status")
        if tables_status in (None, "not-run"):
            warnings.append(UNVERIFIED_TABLE_WARNING)
    budget_line = f"- budget: {args.budget} chars (content: {full_len} chars"
    budget_line += ", TRUNCATED)" if truncated else ")"
    warn_block = ["  - (none)"] if not warnings else [f"  - {w}" for w in warnings]
    header = [
        f"# Query packet: {paper_id} -- {title}",
        "",
        f"- paper_id: {paper_id}",
        f"- ask: `{args.ask}`",
        f"- generated_at: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- source_pdf: {manifest.get('source_pdf', 'unknown')}",
        f"- source_sha256: {manifest.get('source_sha256', 'unknown')}",
        budget_line,
        f"- parse_quality: overall={overall}; warnings:",
        *warn_block,
        f"- provenance: {', '.join(provenance)}",
        "",
        "> Scope note: this packet is a budgeted fragment of deterministic",
        "> extraction artifacts. Check the warnings above before trusting a",
        "> layer; quote numbers only from layers whose status is ok.",
        "",
        "---",
        "",
    ]
    write_text(packet_path, "\n".join(header) + body + "\n")
    print(f"[packet] ask={args.ask} chars={min(full_len, args.budget)}"
          + (" (TRUNCATED)" if truncated else ""))
    print(f"PACKET: {packet_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
