"""pdf_pipeline_smoke_test.py -- lightweight regression checks for PDF P1.

Builds a tiny synthetic PDF in a temp directory (no fixture files, no
network, no LLM) and exercises the P1 contracts:

  1. ingest succeeds (exit 0) and writes manifest + text layer
  2. re-ingest with an unchanged sha256 is skipped (idempotency)
  3. parse_quality.json is written with ALL six layers
     (text/footnotes/figures/tables/references/citations) and
     P1-unimplemented layers carry status "not-run"
  4. parse_quality.json is written EVEN when ingestion never ran
     (overall=failed, exit 1)
  5. an invalid ask exits 2
  6. a packet over budget carries the TRUNCATED marker, and the packet
     header contains paper_id / source_sha256 / source_pdf / budget /
     parse_quality lines
  7. P1.1 hardening (synthetic artifact dir, no ingest needed):
     an empty footnote layer with inline footnote markers in the text is
     flagged possible_inline_footnotes_in_text and degraded (overall too);
     markdown table blocks with tables layer not-run are flagged
     markdown_table_blocks_present_unverified; packets containing such
     table text carry an explicit UNVERIFIED-table warning
  8. P1.5 render route: pdf_render_page.py writes the page PNG plus a
     renders/index.json provenance entry, refuses an out-of-range page
     (exit 2), and refuses a sha256 mismatch against the manifest (exit 1)
  9. P2 figures: pdf_extract_figures.py pairs the synthetic caption+raster
     figure, writes the crop PNG, the quality report scores the layer ok,
     figure:all packets list the entry with its PNG path, and an unknown
     figure id exits 2
  10. P3 GROBID-required layers fail loudly without a service: reference
      and citation extraction exit 4 against an unreachable GROBID URL,
      and reference/citation asks exit 2 while the layers are absent
      (live GROBID behaviour is exercised in the E2E runs, not here)

Run with the same interpreter that has pymupdf installed:
    py scripts/research/pdf_pipeline_smoke_test.py
Exits 0 on all-pass, 1 on any failure, 3 if dependencies are missing.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LAYERS = ["text", "footnotes", "figures", "tables", "references", "citations"]
NOT_RUN_LAYERS = ["figures", "tables", "references", "citations"]


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, cwd=cwd)


def make_pdf(path: Path) -> None:
    import fitz
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Smoke Test Paper", fontsize=20)
    page1.insert_text((72, 110), "A synthetic document for pipeline regression checks.",
                      fontsize=11)
    # A raster image with a "Figure 1" caption right below it (P2 figures).
    fig_doc = fitz.open()
    fp = fig_doc.new_page(width=100, height=100)
    fp.draw_rect(fitz.Rect(10, 10, 90, 90), color=(0, 0, 1), fill=(0.7, 0.7, 1))
    pix = fp.get_pixmap(dpi=96)
    fig_doc.close()
    page1.insert_image(fitz.Rect(72, 200, 272, 350), pixmap=pix)
    page1.insert_text((72, 368), "Figure 1. Synthetic test figure.", fontsize=10)
    page2 = doc.new_page()
    long_text = " ".join(f"word{i}" for i in range(400))
    page2.insert_textbox(fitz.Rect(72, 72, 520, 760), long_text, fontsize=10)
    doc.save(str(path))
    doc.close()


def main() -> int:
    try:
        import fitz  # noqa: F401
    except ImportError:
        print("SKIP/FAIL: pymupdf not installed -- run: py -m pip install pymupdf pymupdf4llm")
        return 3

    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pdf = tmp / "Smoke_Test_2026.pdf"
        make_pdf(pdf)
        out_root = str(tmp / "artifacts")
        art_dir = tmp / "artifacts" / "Smoke_Test_2026"

        # 1. ingest succeeds
        r = run("pdf_ingest.py", "--pdf", str(pdf), "--out-root", out_root)
        check("ingest exit 0", r.returncode == 0, r.stderr.strip()[-200:])
        check("manifest written", (art_dir / "manifest.json").is_file())
        check("page markdown written", (art_dir / "text" / "pages" / "page-0001.md").is_file())

        # 2. idempotent skip on unchanged sha256
        r = run("pdf_ingest.py", "--pdf", str(pdf), "--out-root", out_root)
        check("re-ingest skipped (sha256 match)",
              r.returncode == 0 and "skipping" in r.stdout, r.stdout.strip()[-200:])

        # 3. quality: all six layers, not-run for unimplemented
        r = run("pdf_quality_report.py", "--pdf", str(pdf), "--out-root", out_root)
        q = None
        qpath = art_dir / "parse_quality.json"
        if qpath.is_file():
            q = json.loads(qpath.read_text(encoding="utf-8"))
        check("parse_quality.json written", q is not None)
        if q is not None:
            layers = q.get("layers", {})
            check("all six layers present", all(k in layers for k in LAYERS),
                  f"present: {sorted(layers)}")
            check("unimplemented layers are not-run",
                  all(layers.get(k, {}).get("status") == "not-run" for k in NOT_RUN_LAYERS),
                  str({k: layers.get(k, {}).get("status") for k in NOT_RUN_LAYERS}))

        # 4. quality is written even with no ingestion at all
        r = run("pdf_quality_report.py", "--paper", "Never_Ingested", "--out-root", out_root)
        q2path = tmp / "artifacts" / "Never_Ingested" / "parse_quality.json"
        q2 = json.loads(q2path.read_text(encoding="utf-8")) if q2path.is_file() else None
        check("quality written without manifest (exit 1, overall=failed)",
              r.returncode == 1 and q2 is not None and q2.get("overall") == "failed")

        # 5. invalid ask exits 2
        r = run("pdf_make_query_packet.py", "--paper", "Smoke_Test_2026",
                "--ask", "nosuchask:1", "--out-root", out_root)
        check("invalid ask exits 2", r.returncode == 2, f"rc={r.returncode}")

        # 6. budget truncation + mandatory header fields
        r = run("pdf_make_query_packet.py", "--paper", "Smoke_Test_2026",
                "--ask", "page:1-2", "--budget", "80", "--out-root", out_root)
        packet = None
        for line in r.stdout.splitlines():
            if line.startswith("PACKET: "):
                packet = Path(line[len("PACKET: "):].strip())
        text = packet.read_text(encoding="utf-8") if packet and packet.is_file() else ""
        check("packet produced for page ask", bool(text), r.stderr.strip()[-200:])
        check("TRUNCATED marker present", "[TRUNCATED at budget 80" in text)
        for field in ["- paper_id: Smoke_Test_2026", "- source_sha256: ",
                      "- source_pdf: ", "- budget: 80 chars", "- parse_quality: overall="]:
            check(f"header field: {field.strip('- :')}", field in text)

        # 7. P1.1 hardening: inline-footnote + unverified-table detection.
        # Built directly as an artifact dir so the page markdown is exactly
        # the FRL-like failure shape observed in the P1 trial.
        h_dir = tmp / "artifacts" / "Inline_Fn_2026"
        (h_dir / "text" / "pages").mkdir(parents=True)
        (h_dir / "manifest.json").write_text(json.dumps({
            # Points at the REAL smoke PDF with a fake sha256 so the render
            # route's integrity check (check 8) can observe a mismatch.
            "source_pdf": str(pdf),
            "source_sha256": "0" * 64,
            "tools": {},
        }), encoding="utf-8")
        (h_dir / "footnotes.jsonl").write_text("", encoding="utf-8")  # count=0
        (h_dir / "text" / "pages" / "page-0001.md").write_text(
            "Body text referencing a footnote.<sup>12</sup>\n\n"
            "|col_a|col_b|\n|---|---|\n|0.008|0.015|\n\n"
            "> 12 This footnote text stayed inline in the text layer.\n",
            encoding="utf-8")
        r = run("pdf_quality_report.py", "--paper", "Inline_Fn_2026", "--out-root", out_root)
        hq_path = h_dir / "parse_quality.json"
        hq = json.loads(hq_path.read_text(encoding="utf-8")) if hq_path.is_file() else {}
        fn_layer = hq.get("layers", {}).get("footnotes", {})
        check("inline footnotes flagged possible_inline_footnotes_in_text",
              any("possible_inline_footnotes_in_text" in f for f in fn_layer.get("flags", [])),
              str(fn_layer))
        check("empty-but-inline footnotes layer is degraded (not empty)",
              fn_layer.get("status") == "degraded", str(fn_layer.get("status")))
        check("overall degraded when inline footnotes suspected",
              hq.get("overall") == "degraded", str(hq.get("overall")))
        tb_layer = hq.get("layers", {}).get("tables", {})
        check("markdown tables flagged markdown_table_blocks_present_unverified",
              any("markdown_table_blocks_present_unverified" in f
                  for f in tb_layer.get("flags", [])), str(tb_layer))
        r = run("pdf_make_query_packet.py", "--paper", "Inline_Fn_2026",
                "--ask", "page:1", "--out-root", out_root)
        packet = None
        for line in r.stdout.splitlines():
            if line.startswith("PACKET: "):
                packet = Path(line[len("PACKET: "):].strip())
        text = packet.read_text(encoding="utf-8") if packet and packet.is_file() else ""
        check("packet warns table values UNVERIFIED when tables not-run",
              "table values visible in this packet are UNVERIFIED" in text,
              r.stderr.strip()[-200:])

        # 8. P1.5 render route (real ingested artifact, real source PDF)
        r = run("pdf_render_page.py", "--paper", "Smoke_Test_2026",
                "--page", "1", "--out-root", out_root)
        png = art_dir / "renders" / "page-0001.png"
        check("render exit 0 + RENDER line",
              r.returncode == 0 and "RENDER: " in r.stdout, r.stderr.strip()[-200:])
        check("render PNG written", png.is_file() and png.stat().st_size > 0)
        idx = json.loads((art_dir / "renders" / "index.json").read_text(encoding="utf-8")) \
            if (art_dir / "renders" / "index.json").is_file() else {}
        manifest = json.loads((art_dir / "manifest.json").read_text(encoding="utf-8"))
        check("render index has provenance entry",
              idx.get("renders", {}).get("page-0001.png", {}).get("page") == 1
              and idx.get("source_sha256") == manifest.get("source_sha256"), str(idx)[:200])
        r = run("pdf_render_page.py", "--paper", "Smoke_Test_2026",
                "--page", "99", "--out-root", out_root)
        check("render out-of-range page exits 2", r.returncode == 2, f"rc={r.returncode}")
        # sha mismatch: Inline_Fn_2026's manifest names the real PDF but a fake sha256
        r = run("pdf_render_page.py", "--paper", "Inline_Fn_2026",
                "--page", "1", "--out-root", out_root)
        check("render sha256 mismatch exits 1", r.returncode == 1, f"rc={r.returncode}")

        # 9. P2 figures: caption-anchored extraction, quality scoring, figure ask
        r = run("pdf_extract_figures.py", "--pdf", str(pdf), "--out-root", out_root)
        check("figures extract exit 0", r.returncode == 0, r.stderr.strip()[-200:])
        fj = art_dir / "figures" / "figures.json"
        figs = json.loads(fj.read_text(encoding="utf-8")) if fj.is_file() else {}
        entries = figs.get("figures", [])
        check("figures.json pairs the synthetic caption+raster figure",
              len(entries) == 1 and entries[0].get("page") == 1
              and entries[0].get("method") == "caption+raster"
              and entries[0].get("number") == "1", str(entries)[:200])
        check("figure crop PNG written",
              bool(entries) and (art_dir / entries[0].get("png", "")).is_file())
        r = run("pdf_quality_report.py", "--pdf", str(pdf), "--out-root", out_root)
        q = json.loads(qpath.read_text(encoding="utf-8")) if qpath.is_file() else {}
        fig_layer = q.get("layers", {}).get("figures", {})
        check("figures layer scored ok after extraction",
              fig_layer.get("status") == "ok" and fig_layer.get("count") == 1,
              str(fig_layer))
        r = run("pdf_make_query_packet.py", "--paper", "Smoke_Test_2026",
                "--ask", "figure:all", "--out-root", out_root)
        packet = None
        for line in r.stdout.splitlines():
            if line.startswith("PACKET: "):
                packet = Path(line[len("PACKET: "):].strip())
        text = packet.read_text(encoding="utf-8") if packet and packet.is_file() else ""
        check("figure:all packet lists fig-001 with PNG path",
              "fig-001" in text and "PNG: figures/fig-001.png" in text,
              r.stderr.strip()[-200:])
        r = run("pdf_make_query_packet.py", "--paper", "Smoke_Test_2026",
                "--ask", "figure:9", "--out-root", out_root)
        check("unknown figure id exits 2", r.returncode == 2, f"rc={r.returncode}")

        # 10. P3 layers require GROBID and fail loudly without it
        bad_grobid = "http://localhost:1"
        r = run("pdf_extract_references.py", "--paper", "Smoke_Test_2026",
                "--out-root", out_root, "--grobid-url", bad_grobid)
        check("references exit 4 when GROBID unreachable",
              r.returncode == 4, f"rc={r.returncode}")
        r = run("pdf_build_citation_contexts.py", "--paper", "Smoke_Test_2026",
                "--out-root", out_root, "--grobid-url", bad_grobid)
        check("citations exit 4 when GROBID unreachable",
              r.returncode == 4, f"rc={r.returncode}")
        r = run("pdf_make_query_packet.py", "--paper", "Smoke_Test_2026",
                "--ask", "reference:all", "--out-root", out_root)
        check("reference ask without layer exits 2", r.returncode == 2, f"rc={r.returncode}")
        r = run("pdf_make_query_packet.py", "--paper", "Smoke_Test_2026",
                "--ask", "citation:all", "--out-root", out_root)
        check("citation ask without layer exits 2", r.returncode == 2, f"rc={r.returncode}")

    failed = [n for n, ok, _ in results if not ok]
    print(f"--- {len(results) - len(failed)}/{len(results)} checks passed"
          + (f"; FAILED: {failed}" if failed else " ---"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
