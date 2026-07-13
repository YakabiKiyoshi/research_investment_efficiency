"""pdf_extract_references.py -- P3 references layer via GROBID.

Sends the source PDF to a local GROBID service (/api/processReferences),
parses the returned TEI biblStruct list, and writes
<out-root>/<paper_id>/references/references.jsonl -- one JSON object per
bibliography entry:

    {"id": "ref-001", "raw": "...", "authors": [...], "title": "...",
     "year": "...", "venue": "...", "doi": "...", "source": "grobid",
     "resolved": {"status": "unresolved" | "doi-from-grobid" | "crossref",
                  ...match metadata when resolved...}}

GROBID is REQUIRED for this layer (exit 4 with a clear message when the
service is unreachable; the quality layer then stays not-run). Start it with:
    docker run --rm -d -p 8070:8070 lfoppiano/grobid:0.8.1
and set GROBID_URL (default http://localhost:8070).

External resolution (--resolve crossref) is OPTIONAL and off by default:
it is a network call whose results can change over time, so it is kept out
of the deterministic default path. Matches below the similarity threshold
stay "unresolved" -- never guess-complete a reference.

Usage:
    py scripts/research/pdf_extract_references.py --paper Foo_2020_JAR
        [--out-root outputs/ai/pdf] [--grobid-url http://localhost:8070]
        [--resolve crossref] [--min-score 0.9]

Prints "REFERENCES: <path>" as the last stdout line.
Exit codes: 0 ok, 1 sha256 mismatch, 2 bad args/missing artifacts,
3 missing dependency, 4 GROBID unreachable/failed.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA_VERSION = "1.0"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
DEFAULT_GROBID = "http://localhost:8070"


def eprint(*args):
    print(*args, file=sys.stderr)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def grobid_alive(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/isalive", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def grobid_post_pdf(base_url: str, endpoint: str, pdf_path: Path,
                    timeout: int = 300) -> str:
    """Multipart POST of the PDF to a GROBID endpoint; returns TEI XML."""
    boundary = "----pdfP3Boundary7f2c9d"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="input"; filename="doc.pdf"\r\n',
        b"Content-Type: application/pdf\r\n\r\n",
        pdf_path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{base_url}{endpoint}", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Accept": "application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def text_of(el) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_bibl(bibl, idx: int):
    """One TEI <biblStruct> -> reference dict."""
    authors = []
    for pers in bibl.findall(".//tei:author/tei:persName", TEI_NS):
        surname = text_of(pers.find("tei:surname", TEI_NS))
        fore = text_of(pers.find("tei:forename", TEI_NS))
        name = ", ".join(x for x in (surname, fore) if x)
        if name:
            authors.append(name)
    title = text_of(bibl.find(".//tei:analytic/tei:title", TEI_NS)) or \
        text_of(bibl.find(".//tei:monogr/tei:title", TEI_NS))
    venue = ""
    if bibl.find(".//tei:analytic/tei:title", TEI_NS) is not None:
        venue = text_of(bibl.find(".//tei:monogr/tei:title", TEI_NS))
    date_el = bibl.find(".//tei:imprint/tei:date[@when]", TEI_NS)
    year = date_el.get("when")[:4] if date_el is not None else \
        text_of(bibl.find(".//tei:imprint/tei:date", TEI_NS))[:4]
    doi = ""
    for idno in bibl.findall(".//tei:idno", TEI_NS):
        if (idno.get("type") or "").upper() == "DOI":
            doi = text_of(idno)
            break
    raw = text_of(bibl.find(".//tei:note[@type='raw_reference']", TEI_NS))
    resolved = {"status": "doi-from-grobid"} if doi else {"status": "unresolved"}
    return {
        "id": f"ref-{idx:03d}",
        "tei_id": bibl.get("{http://www.w3.org/XML/1998/namespace}id") or "",
        "raw": raw,
        "authors": authors,
        "title": title,
        "year": year,
        "venue": venue,
        "doi": doi,
        "source": "grobid",
        "resolved": resolved,
    }


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def title_similarity(a: str, b: str) -> float:
    """Token Jaccard on normalized titles -- crude but deterministic."""
    ta, tb = set(norm(a).split()), set(norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def resolve_crossref(ref, min_score: float, timeout: int = 30):
    """Optional network resolution. Only accepts a match whose normalized
    title similarity >= min_score; otherwise leaves the ref unresolved."""
    if not ref["title"]:
        return
    query = urllib.parse.urlencode({
        "query.bibliographic": f"{ref['title']} {ref['year']}".strip(),
        "rows": "1",
    })
    req = urllib.request.Request(
        f"https://api.crossref.org/works?{query}",
        headers={"User-Agent": "research-template-pdf-pipeline"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            items = json.loads(r.read().decode("utf-8"))["message"]["items"]
    except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError):
        ref["resolved"] = {"status": "unresolved",
                           "note": "crossref query failed"}
        return
    if not items:
        return
    cand = items[0]
    cand_title = (cand.get("title") or [""])[0]
    score = title_similarity(ref["title"], cand_title)
    if score >= min_score:
        ref["doi"] = ref["doi"] or cand.get("DOI", "")
        ref["resolved"] = {"status": "crossref", "score": round(score, 3),
                           "doi": cand.get("DOI", ""),
                           "matched_title": cand_title}
    else:
        ref["resolved"] = {"status": "unresolved",
                           "best_score": round(score, 3),
                           "note": f"best crossref match below threshold {min_score}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="source PDF path (paper_id = file stem)")
    group.add_argument("--paper", help="paper_id (artifact dir name)")
    ap.add_argument("--out-root", default="outputs/ai/pdf")
    ap.add_argument("--grobid-url", default=os.environ.get("GROBID_URL", DEFAULT_GROBID))
    ap.add_argument("--resolve", choices=["crossref"], default=None,
                    help="optional external resolution (network; off by default)")
    ap.add_argument("--min-score", type=float, default=0.9,
                    help="title-similarity threshold for --resolve (default 0.9)")
    args = ap.parse_args()

    paper_id = args.paper if args.paper else Path(args.pdf).stem
    art_dir = Path(args.out_root) / paper_id
    manifest = load_json(art_dir / "manifest.json")
    if manifest is None:
        eprint(f"[references] no manifest.json for '{paper_id}'; run pdf_ingest.py first")
        return 2

    pdf_path = Path(args.pdf) if args.pdf else Path(manifest.get("source_pdf", ""))
    if not pdf_path.is_file():
        eprint(f"[references] source PDF not found: {pdf_path}")
        return 2
    actual_sha = sha256_of(pdf_path)
    expected_sha = manifest.get("source_sha256")
    if expected_sha and actual_sha != expected_sha:
        eprint(f"[references] sha256 mismatch vs manifest; re-run pdf_ingest.py")
        return 1

    base = args.grobid_url.rstrip("/")
    if not grobid_alive(base):
        eprint(f"[references] GROBID unreachable at {base} -- start it with:\n"
               "  docker run --rm -d -p 8070:8070 lfoppiano/grobid:0.8.1\n"
               "then set GROBID_URL or pass --grobid-url. The references layer "
               "stays not-run until then.")
        return 4

    try:
        tei = grobid_post_pdf(base, "/api/processReferences", pdf_path)
        root = ET.fromstring(tei)
    except (urllib.error.URLError, OSError, ET.ParseError) as exc:
        eprint(f"[references] GROBID processReferences failed: {exc}")
        return 4

    bibls = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    refs = [parse_bibl(b, i + 1) for i, b in enumerate(bibls)]

    if args.resolve == "crossref":
        for ref in refs:
            if ref["resolved"]["status"] == "unresolved":
                resolve_crossref(ref, args.min_score)

    ref_dir = art_dir / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)
    out_path = ref_dir / "references.jsonl"
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for ref in refs:
            f.write(json.dumps(ref, ensure_ascii=False) + "\n")
    meta = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_sha256": expected_sha or actual_sha,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "grobid_url": base,
        "resolve": args.resolve or "none",
        "count": len(refs),
    }
    (ref_dir / "references_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    n_doi = sum(1 for r in refs if r["doi"])
    n_unres = sum(1 for r in refs if r["resolved"]["status"] == "unresolved")
    print(f"[references] {len(refs)} reference(s); doi={n_doi}, unresolved={n_unres}")
    print(f"REFERENCES: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
