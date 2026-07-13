# 入力スキーマと列マッピング

## 資本投資の標準列

CLI は以下の列名を想定する。Python API では `CapitalColumns` に実際の列名を渡せるため、
元データを rename する必要はない。

| 標準列 | 必須 | 内容 |
|---|---:|---|
| `firm` | yes | 企業 ID |
| `fiscal_year` | yes | 連続性を検証できる整数会計年度 |
| `industry` | model | 産業分類 |
| `assets` | yes | 総資産 |
| `sales` | yes | 売上高 |
| `ppe` | measure | 純有形固定資産 |
| `capex` | measure | 設備投資支出 |
| `rd` | no | R&D 支出 |
| `acquisitions` | no | 買収支出 |
| `sale_ppe` | no | PPE 売却収入 |
| `depreciation` | measure | BH、Richardson、Enomoto 指標に必要な減価償却・償却費 |
| `operating_cash_flow` | no | 営業 CF |
| `net_income` | no | 特別項目前利益等、選択した利益定義 |
| `cash` | no | 現金・短期投資 |
| `debt_current`, `debt_long` | no | 短期・長期有利子負債 |
| `book_equity`, `market_equity` | no | 簿価・時価株主資本 |
| `stock_return` | no | 年次株式リターン |
| `listing_year` | no | 初上場年。なければ初観測年を代理利用 |
| `operating_income_after_depreciation` | no | Richardson V/P の利益 |
| `dividends` | no | 年間配当 |

「必須」は全指標を作るためではなく、パネル基盤としての必須を示す。各関数は必要列が
欠けると該当指標を欠損にし、他の指標は計算を続ける。

BH2006 の国際比較を CLI で推定する場合は `country` も必要である。列名が異なるときは
`fit --country-col <列名>` を指定する。欠損した産業・年度・国などの推定セルキーは一つの
疑似セルへまとめず、推定対象外として診断表に `missing_group_key` を残す。

## 労働投資の標準列

`LaborColumns` は `firm`, `fiscal_year`, `industry`, `employees`, `sales`, `assets`,
`net_income`, `stock_return`, `market_equity`, `quick_assets`, `current_liabilities`,
`debt_current`, `debt_long` を対応付ける。

`quick_assets` は現金・短期投資と売上債権の合計である。`delta_quick` は quick ratio の
前年差ではなく前年比率、レバレッジは短期・長期負債の合計を総資産で割る。流動資産全体を代用する場合は、
クイック比率ではなく流動比率になるため、変数名と感応度を明記する。

## Compustat 例

```python
CapitalColumns(
    firm="gvkey", period="fyear", industry="ff48",
    assets="at", sales="sale", ppe="ppent", capex="capx",
    rd="xrd", acquisitions="aqc", sale_ppe="sppe", depreciation="dp",
    operating_cash_flow="oancf", net_income="ib", cash="che",
    debt_current="dlc", debt_long="dltt", book_equity="ceq",
    market_equity="mve", stock_return="annual_return",
)
```

## NEEDS-FQ での利用

物理パスはハードコードせず、共有 `data_path()` 台帳から解決する。FQ 項目コードは契約版・
加工版により意味が変わり得るため、`C:/Data/fq/definitions` の定義を確認してから
`CapitalColumns` へ渡す。既存 repo で候補になっている列は
`Assets`, `D01021`, `B01063/B01064`, `F01022`, `F01024`, `F01065`, `F01070`,
`H01033`, `H01034`, `C01082`, `C01106`, `MVFE` だが、本パッケージはこれらを暗黙には
採用しない。とくに `H01033/H01034` と `F01022/F01024` を同じ投資式へ重複計上しないこと。

## パネル要件

- 企業×会計年度で一意。
- DataFrame index も一意。
- 企業 ID と年度に欠損なし。
- 連結/単体、会計基準、決算月数を混在させる場合は、入力前に研究デザインを固定。
- 12か月未満・超の変則決算は年率換算するか除外し、その選択を記録。
- 金融業を除くかは研究質問依存であり、ライブラリは自動除外しない。
- winsorization は情報を失う処理なので自動実行しない。`winsorize(..., by=[year])` を明示的に
  呼び、閾値を報告する。
