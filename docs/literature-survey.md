# 投資効率性に関する日米文献サーベイ

最終確認日: 2026-07-14

## 1. 概念の整理

投資効率性は、単一の観測可能な比率ではない。会計研究では主に次の三つを代理変数に
している。

1. **感応度**: 成長機会を統制した後も投資が内部 CF に強く依存するほど、資金制約または
   フリー CF 問題が大きいとみなす。
2. **期待投資からの乖離**: ファンダメンタルズから予測される投資との差を異常投資とし、
   正を過剰、負を過少、絶対値を非効率性とみなす。
3. **条件付投資水準**: 流動性から事前に過剰投資しやすい企業と過少投資しやすい企業を
   分け、会計品質などが前者の投資を減らし後者の投資を増やすかを調べる。

これらは同じ構成概念の代替指標ではあるが、数値の意味は異なる。特に正の残差は
「モデルで説明できない投資」であり、正の NPV がないことを直接観測したものではない。

## 2. 米国・国際研究の展開

### Biddle and Hilary (2006, TAR)

[Accounting Quality and Firm-Level Capital Investment](https://doi.org/10.2308/accr.2006.81.5.963)
は、投資–CF 感応度を投資効率性の代理変数とする。国際比較では
`I/K = alpha + beta1 CF/K + beta2 Q + error` を用い、米国・日本の企業内分析では
Hovakimian 型の 10 年ローリング CFSI も用いる。固定資産投資は概ね
`(Delta PPE + depreciation) / lag net PPE`、米国企業内分析の投資は
`capex / lag net PPE` である。国際比較では投資と CF を arctangent 変換し、Q 代理変数を
対数化して国別に企業固定効果を含める。
この論文は米国と日本を直接比較し、銀行の私的情報チャネルが強い日本では当時、会計品質
と投資効率性の関係が弱いという制度的予測を示した。

### Richardson (2006, RAST)

[Over-investment of Free Cash Flow](https://doi.org/10.1007/s11142-006-9012-1) は投資を
維持投資と新規投資に分ける。総投資は R&D、設備投資、買収から PPE 売却収入を控除し、
維持投資を減価償却・償却費で代理する。新規投資の期待値は、ラグ付き V/P、レバレッジ、
現金、企業年齢、規模、株式リターン、前期新規投資、産業・年固定効果で推定する。正の
残差が論文の中心的な過剰投資指標である。

### McNichols and Stubben (2008, TAR)

[Does Earnings Management Affect Firms' Investment Decisions?](https://doi.org/10.2308/accr.2008.83.6.1571)
は、設備投資を期首純 PPE で割り、産業年別に Q と CF から期待投資を推定する。拡張型は
Q の四分位別切片・傾き、前期対数資産成長、前期投資を加える。Q は
`(market equity + assets - book equity) / assets`、CF は営業 CF を期首純 PPE で割る。
変数を産業年内で順位化し `[0,1]`
へ変換してから推定する点が重要である。主たる超過投資はこの Q モデルの残差である。

### Biddle, Hilary, and Verdi (2009, JAE)

[How Does Financial Reporting Quality Relate to Investment Efficiency?](https://doi.org/10.1016/j.jacceco.2009.09.001)
は二つの設計を定着させた。第一に、現金保有の年次十分位と、符号を反転したレバレッジの
十分位を平均して `[0,1]` にした `OverFirm`（`OverI`）を作る。第二に、総投資を前期の
売上成長だけで説明する回帰を Fama-French 48 産業×年、20 観測以上のセルで推定する。
残差の下位四分位を過少、上位四分位を過剰、中間をベンチマークに分類する。総投資は
`capex + R&D + acquisitions - PPE sales` を前期総資産で割る。

### Chen, Hope, Li, and Wang (2011, TAR)

[Financial Reporting Quality and Investment Efficiency of Private Firms in Emerging Markets](https://doi.org/10.2308/accr-10040)
は Biddle 型を非上場企業へ拡張する際、売上減少ダミーと売上成長との交差項を加え、売上が
増加する局面と減少する局面で期待投資の傾きを分ける。この非対称仕様は、日本企業を使う
既存 repo `research_umezawa` にも部分実装されていた。

### Jung, Lee, and Weber (2014, CAR)

[Financial Reporting Quality and Labor Investment Efficiency](https://doi.org/10.1111/1911-3846.12053)
は投資対象を労働へ広げる。純雇用を売上成長、ROA とその変化、リターン、期首規模順位、
クイック比率と変化、レバレッジ、小幅赤字ビン、産業固定効果で予測し、残差の絶対値を
労働投資非効率性とする。残差と実際の純雇用の符号から、過剰採用、過少解雇、過少採用、
過剰解雇を区別できる。

### Goodman et al. (2014, TAR) と後続研究

[Management Forecast Quality and Capital Investment Decisions](https://doi.org/10.2308/accr-50575)
は、経営者予想の質と設備投資・買収意思決定の質を結び付ける。イベント固有の買収収益性
は汎用企業年指標ではないため本パッケージの第一段階には含めず、Biddle 型の設備・総投資
フローを提供する。後続の CAR 研究では、異常投資の絶対値が年次中央値を下回る企業を
効率的とする二値指標も使われているため、`ie_efficient_below_median` を併記する。

### Chen, Hribar, and Melessa (2018, JAR)

[Incorrect Inferences When Using Residuals as Dependent Variables](https://doi.org/10.1111/1475-679X.12195)
は、第一段階残差を第二段階の被説明変数にする通常の二段階法が、説明変数間の相関により
係数と標準誤差の双方を歪め得ることを示す。したがって本パッケージは第一段階の係数、
セル別 N、rank、R2、rank deficiency を保存するが、第二段階の通常 OLS を「正しい推論」
として自動提供しない。

## 3. 日本の研究と制度的含意

### サーベイと日米差

榎本正博 (2016) の
[「投資の効率性と財務報告の質の関係」](https://cir.nii.ac.jp/crid/1050001202460228480)
は、Biddle 系列を中心に日本語で測定・理論を整理している。日本ではメインバンクの私的情報
と公的会計情報の代替関係が、米国型の結果をそのまま移植できない主要因になる。

### 2001 年制度変更後の日本企業

[Enomoto, Rhee, Jung, and Shuto (2024)](https://doi.org/10.1016/j.japwor.2024.101280)
は、銀行等保有株式取得機構に関連する 2001 年の銀行株式保有制限後に、会計品質と投資
効率性の正の関係が現れ、主に過剰投資の抑制として表れると報告する。投資は
`(Delta PPE + depreciation) / lag assets`、事前的 `OverI` は Biddle et al. の現金・
逆レバレッジ十分位である。本実装の日本向け主指標はこの定義を再現する。

### 日本語研究での拡張

- 小菅貴行 (2024)
  [「資本予算が過剰投資に与える影響」](https://doi.org/10.24747/jma.32.1_87) は、質問票と
  Richardson の過剰投資フレームワークを結び付ける。
- 清水俊希 (2025)
  [「財務報告の質が労働投資の効率性に与える影響」](https://doi.org/10.34605/jaa.2025.26_57)
  は、日本企業に Jung et al. の異常純雇用を適用し、過大・過小雇用の双方を検討する。

日本の実装では、Compustat の「欠損 R&D = 0」慣行を無条件に採用してはならない。
NEEDS-FQ の定義表で、未開示、非該当、ゼロの区別を確認し、`missing_components="zero"`
と `"propagate"` の感応度を報告すべきである。また、初観測年は上場年ではないため、企業
年齢には Listing データを優先する。

## 4. 実装対応表

| 系列 | 投資変数 | 期待値・条件 | 主出力 | API |
|---|---|---|---|---|
| Biddle-Hilary 2006 | (Delta PPE + dep)/lag PPE、capex/lag PPE | Q、CF または 10 年 CFSI | 感応度/CFSI | `estimate_bh_2006_q_cash_flow`, `cash_flow_sensitivity_index` |
| Richardson 2006 | 新規投資/平均資産 | V/P、Lev、Cash、Age、Size、Return、lag I、FE | 正の残差 | `estimate_richardson_2006` |
| McNichols-Stubben 2008 | capex/lag net PPE | Q、CF（拡張は Q 非線形等） | 順位残差 | `estimate_mcnichols_stubben_2008` |
| BHV 2009 | capex+R&D+acq-sale / lag assets | lag sales growth、産業年セル | 符号、絶対値、四分位 | `estimate_bhv_2009` |
| Chen et al. 2011 | 同上 | 負の sales growth を分離 | 符号、絶対値 | `estimate_chen_2011` |
| JLW 2014 | 純雇用 | 16 のファンダメンタル変数、産業 FE | 異常純雇用 | `estimate_jlw_2014` |
| Enomoto et al. 2024 | Delta PPE + dep / lag assets | lag sales growth、現金・逆 Lev の OverI | 残差分類/条件付投資 | `estimate_enomoto_2024`, `add_overinvestment_likelihood` |

## 5. 推奨報告セット

単一指標だけで「投資効率性」を断定せず、少なくとも次を並記する。

1. BHV/Chen 型の総投資残差と Enomoto 型 PPE 投資。
2. 残差の符号、絶対値、連続 magnitude、四分位分類。
3. Richardson または McNichols-Stubben を代替期待モデルとして用いた結果。
4. 第一段階セル数、セル N、R2、rank deficiency、欠損・ゼロ充当フラグ。
5. 残差を第二段階へ投入する場合、一段階推定または生成変数推論による検証。
6. 日本企業では 2001/2002 年前後、銀行依存度、持合い、上場年の定義に関する感応度。
