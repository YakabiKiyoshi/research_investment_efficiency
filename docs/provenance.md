# 既存 repo からの再利用監査

## 調査した実装

| repo / file | 再利用した知見 | 本実装での変更 |
|---|---|---|
| `research_going_concern/scripts/analysis/py/investment_models.py` | 期待投資残差、負残差の過少投資 indicator/magnitude、Q 感応度 | ゾンビ/CZE/pyfixest 依存を除去。セル診断、複数の原論文仕様、欠損監査を追加 |
| `research_going_concern/scripts/analysis/投資効率性.R` | 日本 FQ の PPE 投資候補、年内 winsorization | 旧物理パス・peer spillover を除去。FQ コードを API に埋め込まず列マッピング化 |
| `research_going_concern/scripts/analysis/過少投資.R` | 産業年セル残差と過少投資分類 | 十分位だけでなく符号、magnitude、四分位、絶対値を分離 |
| `research_quarterly_analysis/scripts/08_group_c_investment.py` | Q/CF 感応度と Richardson 型残差を同時報告する発想 | 開示研究固有の `DiscSCF` と I/O を除去 |
| `research_umezawa/scripts/research/holdings_did_plan_c.py` | 負の売上成長ダミーと傾き交差項、セル N ガード | treatment/DID/CSDID 依存を除去し `estimate_chen_2011` へ一般化 |
| `research_theme_retirement/scripts/62_labor_investment.py` | 異常純雇用の残差構築 | 簡略7変数から JLW 原論文の16変数へ拡張 |
| `research_theme_retirement/scripts/86_investment_efficiency.py` | 資本・労働投資の符号解釈 | ERP イベント固有判定を除去し、汎用の4労働非効率タイプを追加 |
| `research_biddle_hilary_2006` | テンプレート化済みの追試 repo を確認 | 分析コードは骨組みのみだったため、原論文・所蔵 PDF から定義を監査 |

## 意図的に移植しなかったもの

- データの物理パス、NEEDS-FQ 項目コードの暗黙対応。
- 研究固有の標本期間、上場・3月決算・12か月決算フィルタ。
- CZE、ゾンビ企業、ERP、SCF 開示、持株会社 treatment。
- 第二段階の通常 OLS を正しい推論とみなす処理。
- 出力先への暗黙 write。ライブラリ関数は DataFrame を返し、CLI だけが明示的に書き込む。

この分離により、他 repo はデータ取得・標本選択・因果デザインを所有したまま、測定だけを
同じバージョンのパッケージへ委譲できる。
