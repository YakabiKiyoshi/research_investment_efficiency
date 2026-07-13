# データベース資源カタログ（全研究リポジトリ共通）

レイアウト v2（2026-07-12 大規模再編）。正本は `research-template/docs/data/`（sync で各 repo に配布）。
機械可読版: `data-paths.json`、パス解決ヘルパー: `scripts/data/data_paths.py` / `data_paths.R`。

## 大原則

1. **データ本体は GitHub に置かない**（容量制限・ライセンス）。git 管理はカタログ・台帳・ヘルパー・パイプラインコードのみ。
2. **データの正本は `C:\Data\`**（ローカル）。OneDrive でのデータ保持は 2026-07-12 に廃止した。
3. **バックアップは Google Drive（有料 5TB）へのミラー**（設計: `data-pipeline` の backup スクリプト参照）。
4. **コードに物理パスを書かない。** 必ず `data_path("<key>")` で解決する。
   フォルダ構成を将来変えるときは **`data-paths.json` の path だけを更新**する
   （キー名は変えない）。これで全リポジトリ・パイプラインが一斉に追随する。

## ルート

| 名前 | 既定値 | 環境変数オーバーライド |
|---|---|---|
| `data` | `C:\Data` | `RESEARCH_DATA_ROOT` |
| `project` | `~\Documents\project` | `RESEARCH_PROJECT_ROOT` |

別 PC・WSL（`/mnt/c/Data` や `/data`）・外付けドライブでは環境変数を設定するだけでよい。
Dev Container で使う場合は `C:\Data` をマウントして `RESEARCH_DATA_ROOT` を渡す。

## C:\Data の全体像

| フォルダ | 系統 | 取得方法 | 再取得 | バックアップ重要度 |
|---|---|---|---|---|
| `fq\` | NEEDS-FinancialQUEST | FQ アプリの自動運転（.nfq、API 不可） | 可（ただし数日がかり） | 中 |
| `eol\` | eol | Web で手動 DL（一部スクレイピング） | 原理上可・実務上困難 | **高** |
| `needs_disc\` | NEEDS（ディスク購入） | 日経メディアマーケティングから購入 | **不能**（再購入） | **最高** |
| `edinet\` | EDINET XBRL | EDINET API v2（data-pipeline/edinet） | 可（数日がかり） | 中 |
| `original\` | 自作オリジナルデータ | PDF 自動抽出・ハンドコレクト等（`original\audit\` ほか） | **不能** | **最高** |
| ~~`legacy\`~~ | （2026-07-12 廃止） | 参照ファイルは original\・各生成元 repo の outputs\・消費側 repo の data\raw\ に移設して削除 | — | — |
| `others\` | 補助 | RiskFreeRate.csv 等 | 可 | 低 |
| `staging\` | FQ 一時 DL 先 | 自動運転の出力（結合後は削除可） | 可 | 不要 |

パイプラインコードはすべて `project\data-pipeline`（git リポジトリ）にある。

---

## 1. FQ（NEEDS-FinancialQUEST）`C:\Data\fq\`

### 更新パイプライン（手順書: `data-pipeline/docs/自動運転の工程.pdf`）

```
fq\material\*.xlsx（FQ アプリで企業リスト更新）
  → data-pipeline/fq/nfq_generators/*.py で .nfq 生成（→ fq\nfq\）
  → FQ アプリで .nfq 実行（NA の扱いを "NA" に設定してから）
  → staging\fq\<name>\ に xlsx が落ちる
  → 結合スクリプトで fq\raw\*.csv を更新
  → data-pipeline/fq/{merge,stock,others} の R で fq\processed\*.csv を再生成
```

補助リスト（基準統合に必須）: `fq\standard_change\EffectIFRS.csv`（IFRS 移行会計年度）、
`AbolitionUS.csv`（US 基準廃止年度。NA=継続適用）。運用方針（2026-07-12〜）:
XBRL コーパスの年限内（2016-07 以降）は `edinet\dei\` の DEI 抽出から自動構築・検証し、
それ以前は手作業リストを凍結正本として今後もマージする（詳細: `C:\Data\edinet\taxonomy\README.md`）。
項目定義: `fq\definitions\*.pdf`（14 本）。

### 1a. 生データ `fq\raw\`

| ファイル | サイズ | 内容 / 主キー |
|---|---|---|
| `Accounting\{Japan, NonConsolidated, IFRS, US}.csv` | 271–518MB | 年次財務（基準別、1686列、FIRM/NKCODE/ACC＋A01…系） |
| `Accounting\Enomoto\*` | 4.6GB | 榎本氏共有用の統合版（再生成可能な派生物） |
| `Quarterly\{…}` / `QuarterlyTanshin\{…}` | 〜838MB | 四半期（有報ベース／短信ベース、1634列） |
| `Stock\Price.csv` | 5.8GB | 日次株価（DATED, NKCODE, OHLC, VOLUME, 調整係数、37列） |
| `Stock\日次銘柄属性.csv` | 11.3GB | 日次銘柄属性（119列） |
| `Stock\日次銘柄指標.csv` | 9.0GB | 日次銘柄指標（72列）。`日次銘柄指標2003年更新停止.csv`（3.1GB）は旧系列 |
| `Stock\Information.csv` / `Holdings.csv` | 1.1GB / 0.8GB | 発行済株式数・自己株（CSSHS/JSHS/JCSSHS） |
| `Stock\MarketIndex.csv` | 0.4MB | 市場指数（旧名 Index.csv は現存しない） |
| `Others\Blockholder.csv` | 634MB | 大株主 |
| `Others\Forecast.csv` / `Analyst.csv` | 410MB / 199MB | 企業予想／アナリスト予想 |
| `Others\Debt.csv` | 280MB | 企業×金融機関×期の借入残高（1977–2021） |
| `Others\Segment.csv` | 88MB | セグメント |
| `Others\Listing.csv` / `Industry.csv` / `IndustryName.csv` | 小 | 上場異動・日経業種マスタ |
| `Others\FirmHoldings.csv` | 61MB | 企業保有株 |

### 1b. 分析用 `fq\processed\` — 研究リポジトリの主参照先

| ファイル | サイズ | 生成（data-pipeline/fq/） | 内容 |
|---|---|---|---|
| `Accounting.csv` / `AllAccounting.csv` | 522MB / 797MB | `merge/01.Merge.R` | 基準統合済み年次財務 |
| `AccountingExp.csv` | 1.25GB | `merge/02.Calculation.R` | **年次メイン DB**（2155列、業種・市場・株価・EA_Adj・利益計算済み。その他金融業52除外） |
| `Quarterly.csv` → `QuarterlyExp.csv` | 880MB / 946MB | `merge/MergeQuarterly.R` → `CalculationQuaterly.R` | 四半期（有報ベース） |
| `QuarterlyTanshin.csv` → `QuarterlyTanshinExp.csv` | 932MB / 623MB | `merge/MergeQuarterlyTanshin.R` → `CalculationQuaterlyTanshin.R` | 四半期（短信ベース、EA_Adj 付き） |
| `PriceExp.csv` / `PriceFiscal.csv` | 3.35GB / 143MB | `stock/Stock.R` | 日次株価拡張版／決算期末対応版 |
| `IndicatorExp.csv` / `IndicatorFiscal.csv` | 1.0GB / 36MB | 同上 | 日次時価総額／決算期末対応版 |
| `ListingExp.csv` | 21MB | `others/Listing.R` | 決算期×上場市場（2022-04 再編対応） |
| `Mothers.csv` ほか | 小 | `merge/02.Calculation.R` 等 | マザーズリスト等 |

主キー: 年次系 `NKCODE`×`ACC`、日次系 `NKCODE`×`Date/DATED`。`SECCODE`・`FIRM` 併載。

---

## 2. eol `C:\Data\eol\`

Web 上のデータベンダー。検索結果 CSV（`eoldb-results_<timestamp>.csv`、先頭 4 行前置き
= `skip=4`）を手動 DL して `raw\` に置く。`data-pipeline/eol/*.R` が `processed\` を生成。

| raw サブフォルダ | 件数 | processed 出力 | 内容 |
|---|---|---|---|
| `AnnualReport\` | 66 | `AnnualReport.csv` | 有報の提出日・提出ラグ |
| `QuarterlyReport\` | 14 | `QuarterlyReport.csv` | 四半期報告書の提出日 |
| `EarningsAnnouncement\` | 912 | `Tanshin.csv`（63MB） | 決算発表日イベント（FQ 突合、2002–2023） |
| `業績・配当予想\` | 89 | `data_mf.csv` / `data_div.csv` | 業績／配当予想修正イベント |
| `FirmList\` | 66 | — | 企業リスト |

---

## 3. NEEDS ディスク購入データ `C:\Data\needs_disc\`

日経メディアマーケティングから購入（買い切り・**再取得不能**。フォルダ名サフィックス=購入日）。
各フォルダに定義書（`*_出力項目一覧.xls` / `CG_def.xlsx`）同梱。
内容: 役員（サマリー・詳細）、監査法人・監査意見、**監査報酬**（20190509 版）、
株主構成、コーポレートガバナンス報告書関連（2015/2018/2019 各版）。

## 4. EDINET XBRL `C:\Data\edinet\`

| フォルダ | 内容 |
|---|---|
| `xbrl_reports\` | 有報・四半期報告書の XBRL zip 原本（2016-07〜2026-07、163,243 ファイル・63GB）。`manifest.csv`・`state_xbrl.sqlite`・`progress.json`。**内部の絶対パスは移行時に C:\Data へ更新済み** |
| `database_annual_xbrl\` | 有報 XBRL 解凍済コーパス（146GB）＋ `edinet_base.sqlite`（documents 45,783 件 2016–2024、**監査報告書 AuditDoc XBRL 含む** → KAM・GC 文言が取れる） |
| `average_age\` | 平均年齢抽出の実行例（テキストブロック抽出パターンの参考） |
| `taxonomy\` | 金融庁 EDINET タクソノミ公式参照資料（2013〜2026 全年版の要素リスト・更新概要・DEI 設定値一覧・`dei_elements_by_edition.json`。README.md に出典 URL・取得日・確認済み事実。DEI 27要素は全年版不変、AccountingStandardsDEI 許容値 = Japan GAAP / US GAAP / IFRS / JMIS） |
| `dei\` | 有報・四半期報告書の DEI 抽出パネル（`dei_annual.csv`・`dei_quarterly.csv`。会計基準・連結有無・会計期間。生成: `data-pipeline/edinet/extract_dei.py`。`fq\standard_change\` の自動構築・連結優先フラグ検証の入力） |

取得・DB 構築ツール: `data-pipeline/edinet/`（EDINET API v2、`EDINET_API_KEY`）。再実行で差分取得。

## 5. その他

| 所在 | 内容 |
|---|---|
| `C:\Data\original\audit\` | **監査オリジナルデータ**: AuditDate.csv（会社法監査報告書日 = 日本の ARL の正。監査報告書 PDF から自動抽出）、audit_report_date_jigyo.csv（事業報告ベース抽出）、AuditDateYuho.csv（有報ベース・比較用）、AuditFee.csv、AuditOpinion.csv、HandCollect 系、DatabaseAQ.csv、ForecastFirst.csv（FRL 版。legacy\management_forecast の正本とは別バージョン）。※FQ 切り出しの複製（AccountingExp・Segment・Listing・VolumeFE）は再取得可能なため 2026-07-12 に削除済み |
| `C:\Data\original\audit\proxy_statement_pdfs\` | **招集通知 PDF 原本**（97GB・11.3万件、年別 2004〜。eol スクレイピングで取得、保護解除済み）。AuditDate 抽出の元データ。最悪 eol から再取得可能だが労力大 |
| `C:\Data\original\audit\proxy_statement_texts\` | 招集通知テキスト（8.9GB、eigyo_101 形式）。PDF→txt 抽出結果で `audit_report_date_jigyo.csv` の直接入力。抽出パイプライン: `data-pipeline/audit_date/`（スクレイピング→解凍・保護解除→PDF→txt→mining） |
| `C:\Data\others\RiskFreeRate.csv` | 無リスク金利 |
| `C:\Data\original\geertsema\` | Geertsema-Lu 類似度データ（database_peers.csv 3.3GB・database.csv・同業他社\。旧環境生成で再現困難） |
| `C:\Data\original\kam\` | KAM ハンドコレクト一式（Data\・Output\） |
| （旧 legacy\ の移設先） | jones_1991 → `research_jones_1991\outputs\Data`、capm → `research_capm\outputs\Data`、management_forecast → `research_management_forecast\outputs\Data`、quarterly_project の Tanshin/Forecast → `research_english_disclosure\data\raw\quarterly_project`、going_concern・quarterly_project の repo コピーは rgc_erc_lane\data\raw に既存。earnings_momentum の Data は FQ マスターから再抽出する方式に変更 |
| `C:\Data\staging\fq\` | FQ 自動運転の一時 DL 先（結合後は削除してよい） |
| `project\Methodology\`（別 repo） | 研究方法論ナレッジベース（手法別文献。`data_path("methodology_dir")`、索引 `Methodology/README.md` を grep） |

### プロジェクト間参照（cross-project outputs）

別プロジェクトの成果物を使うときも `data_path("xproj_...")` で解決する（ハードコード禁止）。
既知: `xproj_peer_weights_dir`・`xproj_ml_discretionary_accruals`・
`xproj_ind_discretionary_accruals`（research_industry_classification 生成）、
`xproj_conservatism_parquet`（research_conditional_conservatism 生成）、
`xproj_managerial_ability_scores`・`xproj_managerial_ability_scores_6input`・
`xproj_managerial_ability_scores_trailing5`
（research_managerial_ability_score 生成）。
新しい依存を使う場合はここと data-paths.json に `xproj_` キーを追加して sync で配布する
（root=project の相対パス）。生成前は `data_path(..., must_exist=False)` で参照し `[--]`。

---

## 利用ルール

1. データ本体は GitHub に置かない。`data/`・`outputs/` は git 管理外（全 repo 共通）。
2. 小さいマスタ類は repo の `data/raw/` に手動コピーし、repo の `docs/data-sources.md` に
   「repo 内パス｜原本キー｜内容」を 1 行記録。
3. GB 級ファイルはコピーせず、必要列だけ `data/processed/*.parquet` に抽出
   （duckdb か `data.table::fread(select=)`）。どのキーからどの列を取ったかを抽出コードに明記。
4. **パスのハードコード禁止。** `data_path("<key>")` のみ。環境が違うときは
   `RESEARCH_DATA_ROOT` で上書き。

## フォルダ構成を変更するときの手順

1. `C:\Data` 内でフォルダを移動・改名する。
2. `research-template/docs/data/data-paths.json` の該当 `path` を更新（**キー名は不変**）。
3. `data-pipeline/docs/data/data-paths.json` に同ファイルをコピー。
4. sync（`research-template/scripts/sync-template-tools.ps1`）で各 repo に配布。
5. `py scripts/data/data_paths.py` を実行して全キーが `[OK]` になることを確認。

## 既知の注意点・履歴

- **2026-07-12**: OneDrive（FQ・Database）と Desktop から C:\Data へ全面移行（レイアウト v2）。
  パイプラインコードは `data-pipeline` repo に移設。旧 OneDrive\R は凍結アーカイブ。
- 旧 R スクリプトの相対パス（`../../../Database/FQ/` 等）・旧 OneDrive 絶対パスは解決しない。
  出会ったら `data_path()` に書き換える。
- OneDrive テナント「公立大学法人大阪」の旧パスを参照するコードが一部リポジトリに残存（無効）。
- `staging\fq\` と `fq\raw\Accounting\Enomoto\`・`fq\processed\All*.csv` は再生成可能な中間物。
