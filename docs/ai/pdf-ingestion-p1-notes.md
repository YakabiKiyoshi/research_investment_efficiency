# PDF ingestion P1 — E2E 検証記録（2026-07-09）

実装: `research-template` commit `5fed39e`（P1 本体）＋ hardening follow-up。
検証はすべて決定論的ローカル実行（LLM・Codex・ネットワーク不使用）。

## E2E 対象と結果

### 1. 実論文（現実的ケース）

- **対象 PDF**: `research_earnings_momentum/docs/papers/Akbas, Jiang, Koch (2017, The Accounting Review) The Trend in Firm Profitability and the Cross-Section of Stock Returns.pdf`
- **page count**: 32
- **extracted sections**: 見出し 34 件 → `text/sections.json`
- **extracted footnotes**: 9 ブロック（`source: heuristic`、正しいページ・マーカー付き）
- **parse_quality**: overall=ok、text=ok（empty page 0）
- **packet 実測**: `abstract` 835 字 / `footnote:all` 7,201 字 / `section:conclusion`
  15,077 字で TRUNCATED 発動 — 全文（~10 万字規模）を context に入れず消費できることを確認
- **冪等性**: 再実行は sha256 一致で skip
- 生成アーティファクトは検証後に template リポジトリから削除済み（再生成可能。
  実運用では所有プロジェクト側の `outputs/ai/pdf/` に生成する）

### 2. 最小 PDF（template 自身の `paper/build/main.pdf`、1 ページ）

- ingest / quality / packet（quality・toc）/ エラー経路（不正 ask → exit 2）すべて成功

## Known limitation（実測で確認）

- **heuristic footnotes は隣接する複数脚注を 1 ブロックに結合することがある**。
  実測例: Akbas et al. の fn-001 に marker 1–3 の 3 脚注が同居。
  → 対処: `source: heuristic` の footnote は必ず spot-check（parse_quality の
  footnotes 層が `degraded`＋flag で警告する）。GROBID 有効時（P3）は TEI 由来になり改善。
- figures / tables / references / citations は P1 未実装（`status: not-run`）。
- スキャン PDF は OCR 非対応（text=failed → needs_visual_check で視覚確認に誘導）。
- GROBID unavailable は failed ではなく **degraded**（text 層と packet 消費は成立）。

## Commands used（検証コマンド）

```powershell
# 取り込み（workflow 経由。summary は outputs/ai/workflows/<ts>_pdf-ingest/）
powershell -File scripts\ai\run-ai-workflow.ps1 -Workflow pdf-ingest -Target <path>.pdf

# 個別実行（検証時は scratchpad venv の python で実行した）
py scripts\research\pdf_ingest.py --pdf <path>.pdf
py scripts\research\pdf_quality_report.py --pdf <path>.pdf
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask quality
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask footnote:all
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask "section:conclusion"

# regression check（16 checks: 冪等 skip / 全 6 層 / not-run / quality 常時生成 /
# invalid ask exit 2 / TRUNCATED / packet 必須ヘッダー）
py scripts\research\pdf_pipeline_smoke_test.py
```

## Generated artifacts（レイアウト）

```
outputs/ai/pdf/<paper_id>/
  manifest.json          sha256・ツール版・層 status（未実装層 = not-run）
  parse_quality.json     6 層（text/footnotes/figures/tables/references/citations）
  text/full.md           ※直接 Read 禁止（packet 生成の内部素材）
  text/pages/page-NNNN.md
  text/sections.json
  footnotes.jsonl        本文から分離
  query-packets/NNNN/packet.md   Claude が読む唯一のファイル
                                 （paper_id / source_pdf / sha256 / budget /
                                  parse_quality warnings / TRUNCATED を必ず含む）
```

## 依存導入（初回のみ）

- `py -m pip install -r requirements.txt`（P1 の必須は `pymupdf` `pymupdf4llm` の 2 つ）
- venv の場合: `py -m venv .venv` → `.venv\Scripts\python -m pip install -r requirements.txt`
  → スクリプトは `.venv\Scripts\python` で起動
- **ホスト `py` に未導入のまま `pdf-ingest` workflow を実行すると step-ingest が
  exit 3 で失敗する**（エラーメッセージに導入コマンドが出る）
- GROBID（P3 で必須、P1 は任意）: 稼働中のサービスを用意し、`GROBID_URL=http://localhost:8070` を設定する。
