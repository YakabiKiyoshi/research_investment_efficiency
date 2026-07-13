# 方法と出力契約

## 投資フロー

`add_capital_investment_inputs()` は元の列を保持し、`ie_` 接頭辞の列を追加する。

| 出力 | 定義 | 根拠 |
|---|---|---|
| `ie_inv_bhv_total` | `(capex + rd + acquisitions - sale_ppe) / lag assets` | Biddle et al. (2009) |
| `ie_inv_richardson_new` | `(total investment - depreciation) / average assets` | Richardson (2006) |
| `ie_inv_bh_fixed_assets` | `(PPE - lag PPE + depreciation) / lag net PPE` | Biddle-Hilary (2006) 国際比較 |
| `ie_inv_enomoto_ppe` | `(PPE - lag PPE + depreciation) / lag assets` | Enomoto et al. (2024) |
| `ie_inv_ms_capex` | `capex / lag net PPE` | McNichols-Stubben (2008) |
| `ie_operating_cash_flow_assets` | `CFO / lag assets` | 総投資モデル用 |
| `ie_cash_flow_net_capital` | `(net income + depreciation) / lag net PPE` | Q/CF 感応度用 |
| `ie_cash_flow_ms_net_capital` | `operating cash flow / lag net PPE` | McNichols-Stubben (2008) |
| `ie_tobin_q_ms` | `(market equity + assets - book equity) / assets` | McNichols-Stubben (2008) |
| `ie_market_leverage_long_debt` | `long debt / (long debt + market equity)` | Biddle et al. (2009) OverI |
| `ie_market_leverage_total_debt` | `total debt / (total debt + market equity)` | 日本向け代替 K-structure |

年度ギャップをまたぐラグは既定で欠損とする。`period` は連続性を検証できる整数の会計年度を
推奨する。分母ゼロまたは非正の資産・PPE を使う比率は欠損になる。

## 欠損コンポーネント

R&D、買収、PPE 売却、減価償却の行単位の欠損は、Compustat 系研究ではしばしばゼロとされる。
既定の `missing_components="zero"` はこれを再現するが、`ie_missing_*` フラグを必ず残す。
ただし、減価償却列が存在しない、または全行欠損である場合は構造的な情報欠落とみなし、
ゼロ充当しない。`ie_source_unavailable_depreciation` が真になり、同項目を使う投資指標は
欠損となる。配当も同様に、利用可能な列の行欠損だけを既定でゼロとし、列全体が利用不能なら
V/P を欠損にする。配当の行欠損処理は `missing_dividends` で独立に変更できる。
短期負債・長期負債も、利用可能な列の行欠損だけをゼロにできる。一方が列ごと利用不能な
場合は総負債を片側だけで代用せず、総負債を使うレバレッジと Q を欠損にする。長期負債
単独の市場レバレッジは、長期負債列が利用可能なら引き続き計算する。
日本データで未開示とゼロを区別できないときは `"propagate"` を主仕様または感応度にする。
capex、PPE、資産、売上は中核項目なので、欠損を自動的にゼロへ置換しない。

## 期待投資推定

`fit_expected_investment()` は次を返す。

- `panel`: 期待値、残差と派生指標を付けた企業年パネル。
- `coefficients`: セルまたは pooled model の全係数。
- `diagnostics`: status、N、design rank、パラメータ数、残差自由度、rank deficiency、
  固定効果の処理方法、R2、adjusted R2。
- `specification`: 安定した仕様 ID。

セル N が `min_obs` 未満なら `small_cell`、残差自由度が `min_residual_df` 未満なら
`insufficient_residual_df` と記録して推定しない。完全な多重共線性がある場合は最小二乗の
一般解を返すが、`rank_deficient=True` とする。欠損セルキーは `missing_group_key` として
別記し、疑似的な産業年セルを作らない。`panel` の `ie_model_outcome` は実際に回帰へ投入した
尺度の目的変数であり、推定行では `ie_model_outcome = ie_expected + ie_residual` が成り立つ。
固定効果カテゴリが1観測しか持たない行は傾きの識別に寄与せず残差が機械的にゼロになるため、
反復的に除外する。`ie_fixed_effect_singleton` と診断表の `singleton_fixed_effect_n` に記録する。
固定効果をwithin変換で吸収する仕様では、`coefficients` は傾き係数だけを返し、企業ごとの
切片は大規模な表として生成しない。`fixed_effect_method="absorbed"` で判別できる。

## 残差派生指標

すべての資本投資モデルは以下を返す。

| 出力 | 意味 |
|---|---|
| `ie_residual` | 実績 - 期待投資。正=モデル上の過剰、負=過少 |
| `ie_inefficiency` | `abs(residual)` |
| `ie_efficiency` | `-abs(residual)`。大きいほど効率的 |
| `ie_overinvestment` | `max(residual, 0)` |
| `ie_underinvestment` | `max(-residual, 0)` |
| `ie_*_indicator` | 残差符号による 0/1 |
| `ie_residual_group` | 年内順位の下位25%=under、上位25%=over、中間=benchmark |
| `ie_efficient_below_median` | 絶対残差が年次中央値未満なら1 |

四分位分類と符号分類は同一ではない。符号分類はゼロからの方向、四分位分類は年内で最も
極端な企業を表す。

## 事前的過剰投資可能性

`add_overinvestment_likelihood()` は、年内で現金保有を十分位化し、市場レバレッジの符号を
反転して十分位化した後、両者の平均を `[0,1]` で返す。既定は Biddle et al. の長期負債
ベースである。日本データで総負債 K-structure を使う場合は
`leverage_col="ie_market_leverage_total_debt"` を指定する。高い値ほど流動性が高く、事前に
過剰投資しやすいとする。これは実現した過剰投資残差ではない。

## CFSI

`cash_flow_sensitivity_index()` は各企業のローリング窓で次を計算する。

```text
CFWAI = sum_s[(max(CF_s, 0) / sum max(CF, 0)) * I_s]
AI    = mean_s(I_s)
CFSI  = CFWAI - AI
```

既定は 10 年すべてが揃う窓である。`lag_cash_flow=True` は投資年に対して CF を1期遅らせる
Biddle-Hilary の代替定義に対応する。既定列は米国企業内分析の `capex / lag PPE` と
`(net income + depreciation) / lag PPE` で、CF 合計がゼロなら欠損。
`require_consecutive=True` では年度列を数値として解釈できる必要があり、ローリング窓内に
年度ギャップまたは投資・CFの内部欠損があれば、その窓の CFSI を欠損にする。

国際比較の直接回帰 `estimate_bh_2006_q_cash_flow()` は、固定資産投資と CF を期首純 PPE
で割り、それぞれ arctangent 変換し、Q 代理変数を対数化して国別・企業固定効果付きで
推定する。企業固定効果はwithin変換で吸収し、企業数に比例する密なダミー行列は作らない。
`transform_like_paper=False` は利用者が同じ変換を済ませた場合に限る。

## McNichols-Stubben の順位仕様

`estimate_mcnichols_stubben_2008()` は原論文の Q（`MVE + assets - book equity`）と営業 CF を
使う。まず産業年ごとに回帰の完全ケースを確定し、outcome とすべての連続説明変数を
`[0,1]` に順位変換する。`augmented=True` では順位化した Q から四分位ダミーを作り、
`rank(Q) × quartile dummy` として傾き交差項を構築する。ダミーや交差項自体を再順位化しない。
このため `ie_residual` の単位は元の capex 比率ではなく順位である。監査用に
`ie_ms_outcome_rank`、`ie_ms_q_rank` などの投入値も返す。

## Richardson の条件付け変数

`estimate_richardson_2006()` は前期の V/P、簿価負債比率、現金保有、企業年齢、企業規模、
株式リターン、前期新規投資を連続説明変数とし、産業固定効果と年度固定効果を加える。
V/P は Ohlson 型の資産内在価値を時価株主資本で割った成長機会の逆代理変数である。

## 労働投資

`add_labor_investment_inputs()` は Jung-Lee-Weber の16説明変数を構築し、
`estimate_jlw_2014()` は原論文の式に従い、産業固定効果付き pooled OLS を推定する
（産業年セル別推定や年度固定効果への置換はしない）。主出力は
`ie_labor_absolute_abnormal_net_hiring`。実際の純雇用と残差の符号を組み合わせ、
`over_hiring`、`under_firing`、`under_hiring`、`over_firing` も返す。
quick ratio の変化は前年差ではなく前年比率、期首レバレッジは短期負債と長期負債の合計を
総資産で割った値である。

## 推論上の制約

このパッケージの OLS は指標構築の第一段階であり、第二段階の標準誤差を提供しない。
説明変数 `X` と第一段階の説明変数 `Z` が相関する状況で `residual ~ X` とすると、生成された
残差を通常データとみなす推論は不正確になり得る。可能なら `investment ~ Z + X` の一段階
仕様を主分析にし、残差型を測定の頑健性として位置付ける。
