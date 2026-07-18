# Enomoto et al. (2024) 再現報告

## 結論

本成果は exact replication ではなく、利用可能な FQ raw 項目による再構成 core である。原論文の NLI 相互保有、外国人・金融機関持株、PPE 取得債務2項目、長期引当金が欠けるため、Table 3 の一致を主張しない。連結財務諸表のみを用い、単独への fallback は行っていない。

## 版の扱い

仕様は入手できた2020年SSRN working paperから復元し、2024年最終版の書誌情報とDOIを確認した。ただし最終accepted manuscript本文をローカルで取得できていないため、working paperから最終版への表・変数・標本変更は未検証である。

## 主レーン（raw complete-case）

| lane                  | period    |   n | status                                                 |   firms |   min_year |   max_year |         r2 |
|:----------------------|:----------|----:|:-------------------------------------------------------|--------:|-----------:|-----------:|-----------:|
| history_reconstructed | 1986-2001 |   0 | insufficient                                           |     nan |        nan |        nan | nan        |
| history_reconstructed | 2002-2013 |   0 | insufficient                                           |     nan |        nan |        nan | nan        |
| history_reconstructed | 2014-2024 |   0 | insufficient                                           |     nan |        nan |        nan | nan        |
| cf_statement          | 1986-2001 |   0 | insufficient                                           |     nan |        nan |        nan | nan        |
| cf_statement          | 2002-2013 |  69 | reconstructed_core_missing_ownership_and_full_controls |      27 |       2006 |       2009 |   0.363224 |
| cf_statement          | 2014-2024 |   0 | insufficient                                           |     nan |        nan |        nan | nan        |

対象raw項目のitem-level SourceMissingを検証できないため、主レーンは欠損を0にせずcomplete-caseとした。history-reconstructed lane は全期間で推定標本が0件となった。reported-CF lane は2006--2009年に69件（27社）のみ残り推定できたが、極端に疎である。その他の期間は0件である。

## missing-as-zero proxy感応度

| lane                  | period    |     n |   firms |   min_year |   max_year |         r2 | status                                                 | missing_item_policy               |
|:----------------------|:----------|------:|--------:|-----------:|-----------:|-----------:|:-------------------------------------------------------|:----------------------------------|
| history_reconstructed | 1986-2001 |  7414 |    1220 |       1987 |       2001 |   0.243742 | reconstructed_core_missing_ownership_and_full_controls | missing_as_zero_proxy_sensitivity |
| history_reconstructed | 2002-2013 | 21608 |    2783 |       2002 |       2013 |   0.193235 | reconstructed_core_missing_ownership_and_full_controls | missing_as_zero_proxy_sensitivity |
| history_reconstructed | 2014-2024 | 23287 |    2827 |       2014 |       2024 |   0.222985 | reconstructed_core_missing_ownership_and_full_controls | missing_as_zero_proxy_sensitivity |
| cf_statement          | 1986-2001 |     0 |     nan |        nan |        nan | nan        | insufficient                                           | missing_as_zero_proxy_sensitivity |
| cf_statement          | 2002-2013 | 15764 |    2595 |       2006 |       2013 |   0.205203 | reconstructed_core_missing_ownership_and_full_controls | missing_as_zero_proxy_sensitivity |
| cf_statement          | 2014-2024 | 23305 |    2831 |       2014 |       2024 |   0.219484 | reconstructed_core_missing_ownership_and_full_controls | missing_as_zero_proxy_sensitivity |

以下の係数・安定性結果はすべてこのproxy感応度であり、会計上のゼロを確認した結果ではない。原論文の標本はpre 8,245件、2002--2013年21,139件、合計29,384件である。本再構成との差は `published_sample_benchmark.csv` に示す。これは同一母集団から順に落ちたattritionとは限らず、利用変数、業種分類、FQ収録範囲、working-paperと最終版の差を含む benchmark difference である。AQに5期の事前残差が必要なため、history laneの最初の推定年は1987年、reported-CF laneはFQのCFO開始後に履歴を蓄積して2006年となる。

## AQの符号

AQはfirst-stage残差の直前5年の標準偏差に負号を付けている。したがって値が大きい（0に近い）ほど会計品質が高い。実装は当期残差を含めず、連続した5期が揃う場合だけ値を与える。

## 識別と安定性

2002年開始は銀行株式保有制限法が2002年1月に施行されたという原論文のpre/post区分に従う。1986--2001、2002--2013、2014--2024 を事前固定した。後者は期間延長であり原論文再現ではない。proxyの3区分pooled slope differenceは `missing_as_zero_proxy_regime_slope_differences.csv`、1998--2006年境界感応度は `missing_as_zero_proxy_break_stability.csv` に保存した。いずれも政策効果の因果推定ではない。proxyのreported-CFとhistory-reconstructedの同一2006--2013年比較も明示名付きファイルに保存した。主係数は `core_coefficients.csv`、proxy係数は `missing_as_zero_proxy_coefficients.csv` に分離した。

## 会計データの監査

`statementScope`、`accountingBasis`、`periodMeasure`、`disclosureChannel` を別軸で保持した。raw assets欠損フラグを除外に使い、既存派生列の0を会計上の0とは解釈していない。主レーンでは trading securities、short-term loans receivable、short-term debt、NCI income、extraordinary gain/loss のraw欠損を0に置換せず、算式結果を欠損のままにする。ゼロ補完結果は明示的なproxy感応度として隔離し、主結果には使わない。基準変更は continuity break とした。B01063（純有形固定資産）については `SourceMissingPPEAny` が同じraw項目専用とは確認できないため、当該フラグによる除外はせず年別欠損を開示した。

## moderation の監査

ローカル FirmHoldings は issuer の保有明細（DNKCODE、SHS、AV/BV）だが、NLI の調査母集団、相互保有識別、holder/issuer の完全な双方向対応を確認できない。このため cross-shareholding proxy は作成せず unavailable とした。
