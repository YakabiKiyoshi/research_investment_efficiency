---
description: 論文 PDF を Claude に丸ごと読ませず、ローカルの決定論的パイプライン（PyMuPDF4LLM、オプションで GROBID）で多層アーティファクト化し、必要な断片だけを query packet として消費する運用手順。「この PDF を取り込んで」「論文 X のセクション/脚注/図表を見せて」「PDF をアーティファクト化」のような依頼、またはコーパス規模の文献作業（引用監査・表数値の照合・繰り返し参照）で起動する。単発の 1 質問なら本スキルを使わず Read でページ指定して直接読む方が速い。
---

# PDF ingestion — 多層アーティファクト化と packet 消費

論文 PDF をローカルで決定論的に抽出し（LLM 不使用・再現可能・provenance 付き）、
Claude は **query packet だけ**を読む。

## 絶対の制約

- **PDF 本体と `text/full.md` を main context に読み込まない**（full.md は
  packet 生成の内部素材であり、直接 Read する対象ではない）。消費は常に
  `pdf_make_query_packet.py` 経由（budget 付き断片）。
- **視覚確認（PNG や PDF ページを Read する）は次の 4 つに限定**:
  `parse_quality.json` の `needs_visual_check[]` 項目、ユーザーが明示
  指定した重要図表、表値引用前の照合（`pdf_render_page.py` が `renders/`
  に生成したページ PNG）、および figure ask が返した `figures/fig-*.png`。
  いずれも PDF 本体は開かない。
- 抽出された数値・脚注・引用は、該当レイヤの status が ok になるまで引用
  しない。unresolved の参照を推測で補完しない。
- 内容妥当性の検証は本スキルの範囲外（`citation-check` / `overclaim-check` へ）。

## 使い分け

| 状況 | 手段 |
|---|---|
| 単発の質問（1 論文 1 回きり） | 本スキル不使用。Read でページ指定して直接読む |
| 繰り返し参照・引用監査・表数値の照合・引用ネットワーク | 本スキル（取込 → packet 消費） |

## 手順

### 1. 取り込み（workflow 経由）

```powershell
powershell -File scripts\ai\run-ai-workflow.ps1 -Workflow pdf-ingest -Target docs\papers\Foo_2020_JAR.pdf
```

- ingest（text 層・脚注・manifest）→ quality（parse_quality.json）の 2 ステップ。
  すべてローカル Python（`py` 起動）。Codex・LLM は関与しない。
- アーティファクト: `outputs/ai/pdf/<paper_id>/`（paper_id = ファイル名 stem）。
- 再実行は sha256 一致でスキップ（強制は `--force` をスクリプト直呼びで）。
- GROBID（脚注の高精度化。P3 の参照・引用文脈では必須）はオプション。使う場合は稼働中のサービスを用意し、環境変数 `GROBID_URL=http://localhost:8070` を設定する。不在でも P1 層は degraded で動く。

### 2. 最初に読むのは parse_quality.json だけ

```powershell
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask quality
```

- `overall` と各レイヤの status を確認。`degraded`/`failed` のレイヤは
  そのレイヤを引用に使わない。
- `needs_visual_check[]` があれば、その項目**だけ**視覚確認してよい。

### 3. 質問には packet で答える

```powershell
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask <ask>
# ask: quality | toc | abstract | section:<部分一致> | page:<n>[-<m>]
#      | footnote:<id|all> | figure:<id|番号|all>（要 pdf_extract_figures.py）
#      | reference:<id|all> | citation:<cite-id|ref-id|all>（要 P3・GROBID）
```

- 出力最終行 `PACKET: <path>` のファイルを Read する（それ以外は読まない）。
- budget（既定 15,000 字）超過分は TRUNCATED 表示 — 続きは ask を絞って再発行。
- 脚注は本文に混ざっていない（`footnotes.jsonl` 由来の ask で取る）。

### 4. 表値を引用する場合（P1.5 視覚照合ルート）

```powershell
py scripts\research\pdf_render_page.py --paper <paper_id> --page <n> [--dpi 200]
```

1. packet で表の markdown を取得する（toc に Table 見出しが載るため
   `--ask "section:table 4"` などで取れることが多い）。
2. 該当ページを `pdf_render_page.py` で render する（source PDF の sha256 が
   manifest と照合される。出力: `renders/page-NNNN.png`＋`renders/index.json`）。
3. **引用したいセルだけ** PNG と目視照合し、一致したセルのみ引用する。
   照合済みである旨と provenance（packet 番号・render パス）を記録する。
4. 照合していないセル・行は引用しない。構造化 CSV は P1.5 では作らない
   （信頼できる抽出器が無いため。下記「既知の限界」参照）。

### 5. 図を参照する場合（P2 figures 層）

```powershell
py scripts\research\pdf_extract_figures.py --paper <paper_id> [--dpi 200]
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask figure:all
```

- caption（Figure N / Fig. N）を anchor に同一ページの raster 画像とペアリング
  し、bbox crop を `figures/fig-NNN.png` に生成（`figures/figures.json` が索引）。
- figure ask の packet に載った PNG は視覚確認してよい（上記「絶対の制約」の
  4 番目）。図の内容を引用する前に必ず PNG を実際に見る。
- `method: caption-only` は vector 描画の図（crop 不能）で、PNG は**全ページ
  render**。figures 層が degraded になるので、ページ内で図を目視特定してから
  引用する。`raster-only` は caption の無い大型画像で、装飾の可能性がある。

### 6. 参照・被引用文脈を使う場合（P3、GROBID 必須）

```powershell
py scripts\research\pdf_extract_references.py --paper <paper_id> [--resolve crossref]
py scripts\research\pdf_build_citation_contexts.py --paper <paper_id>
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask reference:all
py scripts\research\pdf_make_query_packet.py --paper <paper_id> --ask "citation:<ref-NNN>"
```

- GROBID 未起動なら両スクリプトとも exit 4（起動コマンドは手順 1 参照）。
  層は not-run のまま — 推測で参照情報を補完しない。
- references: GROBID TEI 由来の書誌（authors/year/title/venue/DOI）。DOI は
  PDF 自体に埋まっている場合のみ付く（`doi-from-grobid`）。`--resolve crossref`
  はオプションのネットワーク解決（既定 off。結果が時間で変わりうるため決定論
  経路から分離。タイトル類似度 0.9 未満は unresolved のまま）。
  **unresolved の参照は書誌事項を引用しない**（絶対の制約）。
- citations: 本文中の引用マーカー＋前後 240 字＋節見出し。
  `citation:<ref-NNN>` で特定文献の被引用文脈を一括取得（引用監査向け）。

### 7. 表の構造化抽出（P2 tables — 延期中）

- `pdf_extract_tables.py`（CSV/HTML/JSON）は**延期中**。PyMuPDF `find_tables`
  は 2026-07 の feasibility test で不合格（罫線の少ない学術誌様式で recall 0%、
  text strategy は散文ページも誤検出しマイナス記号が化ける）。信頼できる
  抽出器が特定できるまで、表値は上記 P1.5 ルート（手順 4）で扱う。

## P1 の既知の限界（明示）

- **heuristic footnotes は隣接する複数脚注を 1 ブロックに結合することがある**
  （実測: TAR 論文で marker 1–3 が fn-001 に同居）。`source: heuristic` の
  footnote は **必ず spot-check 対象**として扱い、引用前に PDF 該当ページと
  照合する。GROBID 有効時は TEI 由来（`source: grobid`）となり改善する。
- **GROBID unavailable は failed ではなく degraded**。parse_quality の
  footnotes 層が `degraded` になるだけで、text 層と packet 消費は成立する。
- **footnotes の count=0 は「脚注なし」を保証しない**。組版によっては
  heuristic が脚注領域を検出できず、脚注本文が text 層にインラインで残る
  （実測: Koga & Yamaguchi (2023, FRL) の P1 trial で、footnotes 層が
  `empty` なのに脚注 12 の本文が section packet 内に残存）。この場合
  parse_quality が `possible_inline_footnotes_in_text` flag を立て、
  footnotes 層は `empty` ではなく `degraded` になる。count=0 でも脚注を
  引用する前にページ packet で該当箇所を確認する。
- **text packet 内に見えている表値は未検証**。pymupdf4llm が本文 markdown に
  混入させた表（parse_quality の `markdown_table_blocks_present_unverified`
  flag、packet の warning 行で明示される）は抽出・照合を経ていない。
  **表値の引用・根拠化は、P1.5 視覚照合ルート（手順 4）で PNG と照合済みの
  セルに限る**。照合していない値は「表があること」の言及に留める。
- **表の構造化抽出（P2 tables）は延期中**。PyMuPDF `find_tables` が実データで
  不合格だったため（詳細: `docs/ai/pdf-ingestion-p1-trial.md`）。ML 系抽出器は
  重依存・非決定論のため不採用。実需が積み上がり信頼できる抽出器が特定できた
  時点で再検討する。
- **figures の検出は caption 前提**。「Figure N / Fig. N」形式の caption が
  無い図（本文中の無ラベル図等）は検出できず、count=0 が「図なし」を保証
  しない（footnotes と同じ注意）。vector 描画の図は `caption-only` になり
  crop 位置は不明（全ページ render で代替）。
- **citations 層の recall は引用スタイル依存**。著者-年式は良好（実測:
  Chordia 117 件 / Koga 85 件）だが、番号上付き式（He & Narayanamoorthy で
  10 件/47 参照）は低く、quality が degraded ＋ flag を立てる。
  **この層から「この論文は X を引用していない」を推論しない**（脚注番号の
  上付きが bibr に誤分類される事象は抽出側で除外済み。meta の
  `skipped_footnote_markers` に記録される）。
- **tables は `status: not-run`**（延期中、手順 7）。表の情報を求められたら
  「構造化抽出は延期中」と正直に伝え、P1.5 ルートで代替する。
- スキャン PDF は OCR 非対応（text 層 failed → 視覚確認で代替）。
- 日本語論文は GROBID の精度が落ちる。parse_quality の flags を尊重する。

## 依存の導入（初回のみ）

パイプラインは `py`（Windows launcher）で起動する。ホストの `py` に依存が
無い場合、`pdf-ingest` workflow は **step-ingest（exit 3）で失敗する**。

```powershell
# a) リポジトリの requirements にまとめて入れる場合
py -m pip install -r requirements.txt

# b) プロジェクト venv を使う場合（グローバル禁止の repo 規約準拠）
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# venv 使用時はスクリプトを .venv\Scripts\python で直接起動する

# c) 最小構成（P1 に必要なのは 2 つだけ）
py -m pip install pymupdf pymupdf4llm
```

軽量 regression check（依存導入後の動作確認にも使える）:

```powershell
py scripts\research\pdf_pipeline_smoke_test.py
```

## トラブルシュート

- `missing dependency`（exit 3）: 上の「依存の導入」を実施。
- 全ページ empty → スキャン PDF（v1 は OCR 非対応)。needs_visual_check に
  従い視覚確認で代替。
- E2E 検証記録・依存導入・既知の限界の詳細: `docs/ai/pdf-ingestion-p1-notes.md`
  （リポジトリ内。原本の作業メモは project ルート `docs/ai/` にもある）。
