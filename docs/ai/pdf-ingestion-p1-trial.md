# PDF ingestion P1 — 実運用トライアル（2026-07-09）

P1 実装（commit `336c0d6`）の実運用検証。E2E 検証（`pdf-ingestion-p1-notes.md`）で
使用済みの Akbas et al. (2017) とは別の実論文 4 本を `pdf-ingest` workflow で取り込み、
`parse_quality.json` と query packet の実用性を確認した。
GROBID は未起動（`not_configured`）。full.md は一切 Read していない
（消費はすべて `pdf_make_query_packet.py` 経由）。

## 対象と結果サマリ

| # | paper_id | pages | headings | footnotes | overall | degraded 層 |
|---|---|---|---|---|---|---|
| 1 | Chordia, Shivakumar (2006, JFE) Earnings and price momentum | 30 | 19 | 16 (heuristic) | degraded | footnotes |
| 2 | He, Narayanamoorthy (2020, JAE) Earnings acceleration and stock returns | 22 | 27 | 16 (heuristic) | degraded | footnotes |
| 3 | Byun, Roland (2022) Quarterly earnings thresholds | 27 | 43 | 13 (heuristic) | degraded | footnotes |
| 4 | Koga and Yamaguchi (2023, FRL) Does mandatory quarterly reporting induce managerial myopic behavior | 11 | 19 | 0 (none / empty) | ok | なし |

- 全 4 本とも text 層は `ok`、`empty_text_pages: 0`、`needs_visual_check: []`。
- warnings は #1–#3 で共通の 1 件のみ:
  「heuristic extraction (GROBID unavailable): adjacent footnotes may be merged
  into one block; spot-check against the PDF before quoting」。#4 は warnings なし。
- figures / tables / references / citations は全論文 `not-run`（P1 仕様どおり）。
- workflow は 4 本とも `execution_status: completed`（1 本あたり十数秒）。
  再実行は sha256 一致で skip（#4 で再確認、冪等）。

## 生成した packet（各 15,000 字 budget、TRUNCATED 発動なし）

| paper | toc | abstract | section:conclusion | footnote:all |
|---|---|---|---|---|
| Chordia-Shivakumar | 668 字 | 865 字 | 7,182 字 | 4,216 字 |
| He-Narayanamoorthy | 1,647 字 | 10,939 字 | 3,901 字 | 7,381 字 |
| Byun-Roland | 2,018 字 | 892 字 | 3,348 字 | 2,949 字 |
| Koga-Yamaguchi | 756 字 | 10,860 字 | 7,563 字 | 0 字（空 packet、正常終了） |

packet ヘッダー（paper_id / source_pdf / sha256 / budget / parse_quality warnings /
provenance）は全 packet で欠落なし。

## packet だけで Claude が使えるか → テキスト層のタスクなら使える

- **構造把握（toc）**: 4 本とも見出し＋ページ番号が取れ、後続の section/page ask の
  足がかりとして十分。特に Koga-Yamaguchi と Byun-Roland は節番号までほぼ完全。
  ノイズはある（Chordia の論文タイトルが「and momentum Earnings price」と語順崩れ、
  Byun-Roland の toc に数式行が見出しとして混入）が、実用を妨げない。
- **abstract**: Abstract 見出しを検出できた 2 本（Chordia 865 字 / Byun 892 字)は
  ピンポイントで清潔。検出できない組版（Elsevier の "a r t i c l e i n f o" 形式:
  He / Koga）は 1 ページ目全体（~11,000 字）へのフォールバックになるが、abstract
  本文は正しく含まれており budget 内。実害なし、ただし toc → page ask より重い。
- **section:conclusion**: 4 本とも結論本文を完全に取得。ページ単位切り出しのため、
  同一ページの表や back matter が混入する（Koga では Table 4 と CRediT 等が同居）。
  混入した表は provenance が明確なので誤引用リスクは低いが、tables 層が not-run で
  ある以上、**そこに見えている数値は引用に使わない**運用を徹底する。
- **footnote:all**: 引用チェック用途に実用的。ただし下記の限界が実測で再確認された。

## 実測で確認した限界（P1 notes の Known limitation の追試＋新規 1 件)

1. **隣接脚注の merge（既知・再現）**: Chordia で 3 件実測 — fn-002 に marker 2+3、
   fn-005 に marker 6+7、fn-011 に marker 13+14 が同居（marker 列が 3, 7, 14, 18 等を
   飛ばしていることからも判別可能）。`source: heuristic` の脚注は引用前 spot-check
   必須、という既存ガイダンスのとおり。
2. **脚注ブロックの途中切断（既知の亜種）**: Byun-Roland fn-007 が
   「...and that also included」で文が切れている。merge と逆方向の失敗
   （ブロック境界の取りすぎ・取り足りなさ）も spot-check 対象。
3. **新規: footnotes `empty` は「脚注なし」を意味しない**。Koga-Yamaguchi は
   footnotes 層が `count: 0, source: none, status: empty` で overall=ok だが、
   本文 packet 内に脚注 12 の本文がインラインで残存している（FRL の組版では
   heuristic が脚注領域を検出できず、text 層に混入したまま）。情報の欠落はない
   （本文 packet で読める）が、「count=0 だから脚注を確認しなくてよい」とは
   読めない。**overall=ok でも footnote 引用時はページ packet で確認する**。
4. **GROBID 未起動時は overall=degraded が実質デフォルト**（脚注のある論文は
   必ず footnotes 層が degraded になるため、今回 4 本中 3 本が degraded）。
   text 層が ok であれば packet 消費は問題なく成立するので、overall=degraded を
   「使えない」と誤読しない。degraded の意味は warnings 行で必ず確認する。

## P2（tables / figures）は必要か → 必要

- **tables: 必要性高い**。今回の 4 本はすべて実証論文で、価値の中心は係数・t 値・
  サンプルサイズ等の表数値。現状それらは (a) not-run のため引用不可、
  (b) pymupdf4llm が本文に混入させた markdown 表として「見えてしまう」
  （Koga の Table 4 実測）— 検証済みレイヤとして取れないのに目に入る、という
  歪んだ状態。表の CSV/PNG 照合付き抽出（P2）が入れば、引用監査・数値照合の
  ワークフローが完結する。
- **figures: 優先度は tables より低い**。今回の 4 本では図への依存度が低く、
  needs_visual_check も空。図が議論の中心になる論文（時系列プロット等）で
  必要になった時点で十分。
- references / citations（P3, GROBID 必須）は今回のトライアル範囲では
  差し迫った不足は感じなかった（footnote:all + 本文 packet で代替可能）。

## P1.1 hardening（本トライアルの発見を受けた対応、同日実装）

トライアルで確認した「未検証情報を誤って信頼しうる」2 経路を塞いだ:

1. **inline footnote 検出** — `pdf_quality_report.py` に
   `possible_inline_footnotes_in_text` を追加。footnotes 層が count=0 のとき、
   本文中の `<sup>N</sup>` マーカーと同じ N で始まる脚注様の行が併存する場合に
   conservative に発火し、footnotes 層を `empty` ではなく **`degraded`**（＋flag）、
   overall も **degraded** にする（上記 Koga & Yamaguchi 型の false negative 対策）。
2. **未検証表値の明示** — `pdf_quality_report.py` に
   `markdown_table_blocks_present_unverified` を追加。text 層に markdown 表様
   ブロックがあり tables 層が `not-run` の場合に tables.flags へ記録。さらに
   `pdf_make_query_packet.py` は、配信する packet 本文に markdown 表様テキストが
   含まれ tables 層が未抽出のとき、warning block に「表値は UNVERIFIED、引用・
   根拠化しない」と明示する。
3. **SKILL.md 更新** — 「count=0 は脚注なしを保証しない」（Koga & Yamaguchi 実測例
   つき）と「text packet 内の表値は未検証。引用は P2 tables 抽出（CSV/HTML/PNG/JSON）
   後」を known limitation に追記。
4. **smoke test 拡張** — 上記 3 点（inline footnote flag＋degraded/overall、tables
   flag、packet warning）を合成アーティファクトで検証するチェックを追加。

## P1.5 — 表値の視覚照合ルート（find_tables 不合格を受けた代替、同日実装）

P2 tables（構造化抽出）は PyMuPDF `find_tables` の feasibility test 不合格により延期:

- `lines` / `lines_strict`（既定）: 既知の表ページ 9/9 で検出 0 件
  （罫線の少ない学術誌様式に線ベース検出は無力）。
- `text` strategy: 散文だけのページでも 60×7 等の偽テーブルを返し（3/3 ページで
  誤検出）、bbox はページ全体、マイナス記号が「�|」に化ける。係数引用における
  符号化けは許容できない。
- 皮肉なことに pymupdf4llm の text 層 markdown は同じ表を正しい「−」付きで
  出力しており、値の忠実度は「未検証」ラベルの text 層のほうが高かった。

代わりに **`pdf_render_page.py`（P1.5、新規依存ゼロ）** を追加。該当ページを
PNG に render（source PDF の sha256 を manifest と照合してから）し、
`renders/index.json` に provenance を記録。表値は「markdown 表値 ↔ PNG の
目視照合が済んだセルのみ引用可」という運用にした（SKILL.md 手順 4）。
packet / parse_quality の warning 文言も render ルートへ誘導するよう更新。
smoke test は 26 checks（render 正常系・範囲外 page exit 2・sha256 不一致
exit 1 を含む）。

### 照合リハーサル（Koga & Yamaguchi, Table 4, p.8, 200 dpi）

packet 0005 の markdown 表値と `renders/page-0008.png` を目視照合した結果:

- **数値セルは全一致**。Panel A–C の係数・t 値・Obs（3380）・Adjusted R² まで、
  spot-check した全セルが PNG と一致（例: Panel A の TREAT\*PRE(−2) 行
  −0.007\*\*\* (−3.990) … 0.008 (1.703)、Panel C の TREAT\*POST(+4) 行
  0.008\*\*\* … 0.031\*\*\*）。マイナス記号も markdown 側で正しく保持。
- **キャプション・注記のテキストには乱れがある**。表注の語順崩れ
  （"Coef- TREAT ficient estimates..."）、Panel C 見出しの「+|6」化け。
  → 数値は照合後に使えるが、**表注の文言引用はページ packet か PNG で
  確認してから**にする。
- 原著の綴り "Paralell"（正: Parallel）が markdown・PNG 双方で一致 — 抽出は
  原文に忠実であることの傍証。

## P2 — figures 層（caption-anchored 抽出、2026-07-09 実装）

tables と異なり feasibility probe は**良好**だったため実装した。probe 実測
（trial 4 本）: 真の図はすべて「Fig./FIGURE N」caption＋同一ページの raster
画像のペアで存在し、caption なし raster は出版社ロゴ（46–73pt）のみ
→ **caption を anchor にした検出**が正解。

- `pdf_extract_figures.py`（新規依存ゼロ）: caption 検出 → 同一ページで
  caption の上にある最近傍 raster とペアリング → bbox crop を
  `figures/fig-NNN.png` に生成、`figures/figures.json` が索引（sha256 検証付き）。
  vector 描画の図は `caption-only`（全ページ render で代替、degraded）、
  caption なし大型画像（≥120pt 両辺）のみ `raster-only`。
- parse_quality の figures 層が実スコアリングに（ok / empty / degraded＋flags）。
- packet に `figure:<id|番号|all>` ask を追加。packet が図の PNG パスを提示し、
  その PNG の視覚確認を sanctioned とした（SKILL.md 手順 5）。
- smoke test: 32 checks（caption+raster ペアリング・crop 生成・quality 採点・
  figure ask・未知 id の exit 2 を含む）。

### E2E（trial 4 本）

| paper | figures | 内訳 |
|---|---|---|
| Chordia-Shivakumar | 0 | 図なし（p.1 ロゴはサイズ閾値で正しく除外） |
| He-Narayanamoorthy | 2 | Fig. 1 (p.9) / Fig. 2 (p.20)、いずれも caption+raster |
| Byun-Roland | 2 | FIGURE 1 (p.5) / FIGURE 2 (p.6)、いずれも caption+raster |
| Koga-Yamaguchi | 0 | 図なし（同上） |

He の fig-001.png を目視検証: チャート全体（軸・凡例・ラベル）が過不足なく
crop されており、caption 記載内容（EAP デシル間 VMAR の時系列）と一致。

既知の限界: 検出は caption 前提のため **count=0 は「図なし」を保証しない**
（無ラベル図は取れない）。vector 図の crop 位置は特定できない（caption-only）。

## P3 — references / citations 層（GROBID、2026-07-09 実装）

- `pdf_extract_references.py`: GROBID `/api/processReferences` の TEI から書誌を
  `references/references.jsonl` に抽出（authors/year/title/venue/DOI、sha256 検証付き）。
  外部解決 `--resolve crossref` はオプション（既定 off — ネットワーク結果は時間で
  変わりうるため決定論経路から分離。タイトル類似度 0.9 未満は unresolved のまま）。
- `pdf_build_citation_contexts.py`: `/api/processFulltextDocument` の TEI から
  本文中の引用マーカー＋前後 240 字＋節見出しを `citations/citation_contexts.jsonl` に。
  references 層と TEI id でリンク（`ref_id`）。**脚注番号の上付きが bibr に
  誤分類される事象を実測**（He で 23 件）→ target なし・数字のみのマーカーは
  除外し、meta の `skipped_footnote_markers` に記録。
- packet ask `reference:<id|all>` / `citation:<cite-id|ref-id|all>` を追加。
- quality: references（unresolved 数を flag）・citations（unlinked 数、および
  contexts < references のとき **recall 低下の degraded flag**）の実スコアリング。
- smoke test: 36 checks（GROBID 不在時の exit 4、層なし ask の exit 2 を含む。
  GROBID 実体は E2E で検証し、smoke はサービス非依存を維持）。

### E2E（GROBID 0.8.1 軽量 CRF 版、trial 4 本）

| paper | refs | DOI 付き | contexts | unlinked | 備考 |
|---|---|---|---|---|---|
| Chordia-Shivakumar | 44 | 0 | 117 | 7 | 著者-年式、recall 良好 |
| He-Narayanamoorthy | 47 | 0 | 10 | 2 | **番号上付き式 → recall 低**（degraded flag 発火） |
| Byun-Roland | 32 | 0 | 53 | 6 | 著者-年式 |
| Koga-Yamaguchi | 50 | 37 | 85 | 4 | FRL は PDF に DOI 埋め込みあり |

ground truth 照合: Koga の ref-041 = Petersen (2009, Rev. Financ. Stud.,
DOI 10.1093/rfs/hhn053) — 実際の書誌と一致。`citation:ref-041` で被引用文脈
3 件（Regression results / Table 3 / Conclusion 節）が正しくリンクされた。

### 運用ノート

- **citations 層から「引用していない」を推論しない**（引用スタイル依存の
  recall。quality の degraded flag を尊重）。
- GROBID 起動: `docker run --rm -d -p 8070:8070 -e JAVA_OPTS="-XX:-UseContainerSupport"
  lfoppiano/grobid:0.8.1`。`JAVA_OPTS` は cgroup v2 環境（Docker Desktop/WSL2）で
  JVM が起動時 NullPointerException でクラッシュする既知問題の回避策（実測）。
- DOI は PDF に埋まっている場合のみ `doi-from-grobid` で付く（軽量版 GROBID は
  consolidation なし）。それ以外は `--resolve crossref` を明示的に使う。

## 環境メモ

- ホスト `py`（Python 3.14）に `pymupdf` はあったが `pymupdf4llm` が未導入で、
  SKILL.md 記載の標準手順（`py -m pip install pymupdf4llm`）で解消。
  導入後 pymupdf / pymupdf4llm とも 1.28.0。
- アーティファクトは `research-template/outputs/ai/pdf/<paper_id>/` に生成
  （source_pdf は `research_earnings_momentum/docs/papers/` を絶対パス参照。
  sha256 が manifest / packet に記録されるため provenance は追跡可能）。
