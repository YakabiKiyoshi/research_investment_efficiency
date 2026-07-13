# Investment Efficiency

会計研究で使われる企業年の投資効率性指標を、データソースに依存しない形で構築する
Python パッケージです。米国の主要研究デザインと、日本企業への主要な適用を同じ API
で比較できます。

## 実装範囲

- Biddle and Hilary (2006): 投資-CF 感応度用の変数と 10 年ローリング CFSI
- Richardson (2006): 期待新規投資と異常投資
- McNichols and Stubben (2008): Q モデル（基本・拡張）の超過設備投資
- Biddle, Hilary, and Verdi (2009): 売上成長モデル、過剰・過少・ベンチマーク分類
- Chen, Hope, Li, and Wang (2011): 売上減少時の傾きを分ける期待投資モデル
- Jung, Lee, and Weber (2014): 異常純雇用による労働投資効率性
- Enomoto et al. (2024): 日本企業向け PPE 投資と事前的過剰投資可能性 `OverI`

残差の符号、絶対値、過剰・過少の magnitude/indicator、年次四分位分類、中央値基準の
効率企業フラグを同時に返します。各指標は元の論文と同じ概念を保ちつつ、列名マッピング
により Compustat、NEEDS-FinancialQUEST、独自パネルのいずれにも利用できます。

## インストール

```bash
python -m pip install -e ".[dev]"
```

別リポジトリの `pyproject.toml` から利用する場合:

```toml
dependencies = [
  "investment-efficiency @ git+https://github.com/YakabiKiyoshi/research_investment_efficiency.git@v0.1.0",
]
```

ローカル開発中は相対パスではなく editable install を推奨します。

```bash
python -m pip install -e ../research_investment_efficiency
```

## 最小例

```python
from investment_efficiency import (
    CapitalColumns,
    add_capital_investment_inputs,
    estimate_bhv_2009,
)

prepared = add_capital_investment_inputs(
    raw_panel,
    columns=CapitalColumns(
        firm="gvkey",
        period="fyear",
        industry="ff48",
        assets="at",
        sales="sale",
        ppe="ppent",
        capex="capx",
        rd="xrd",
        acquisitions="aqc",
        sale_ppe="sppe",
        depreciation="dp",
        operating_cash_flow="oancf",
        cash="che",
        debt_current="dlc",
        debt_long="dltt",
        book_equity="ceq",
        market_equity="mve",
    ),
)

result = estimate_bhv_2009(prepared)
firm_year = result.panel
cell_diagnostics = result.diagnostics
```

入力は DataFrame index と企業・年度の双方で一意である必要があります。年度ギャップを
またぐラグは既定で欠損になり、R&D・買収・PPE 売却などの欠損をゼロ扱いした場合は
監査フラグが残ります。減価償却列がデータ全体で利用不能な場合はゼロと推測せず、同項目を
必要とする指標を欠損にします。

## CLI

```bash
investment-efficiency specs
investment-efficiency prepare --input raw.parquet --output prepared.parquet
investment-efficiency fit --spec bhv2009 --input prepared.parquet --output measures.parquet
```

CLI の `prepare` は標準列名を想定します。列名が異なるデータは Python API の
`CapitalColumns` を使って明示的に対応付けてください。`fit` は `bh2006`、`bhv2009`、
`chen2011`、`enomoto2024`、`richardson2006`、`mcnichols2008-basic`、
`mcnichols2008-augmented` に対応し、レジストリの正式 ID も受け付けます。`bh2006` は
標準で `country` 列を必要とし、別名なら `--country-col` で指定します。係数表と第一段階
診断も別 CSV に保存します。`--min-residual-df` でセルごとの最低残差自由度を設定できます。

## 重要な推定上の注意

残差は推定された量です。残差を別の回帰の被説明変数にする二段階推定は、通常の標準誤差
や係数にバイアスを生じさせることがあります。本パッケージは指標構築と第一段階診断を
提供しますが、第二段階の因果推論を自動的に正当化しません。説明変数を第一段階へ含める
一段階仕様、ブートストラップ、または研究デザインに適した生成変数推論も併記してください。

詳細は [文献サーベイ](docs/literature-survey.md)、
[方法と出力](docs/methodology.md)、[入力スキーマ](docs/input-schema.md) を参照してください。

## 検証

```bash
python -m unittest discover -s tests -v
python examples/quickstart.py
python -m build
```

## ライセンス

MIT。入力データおよび派生データの再配布可否は、各データ提供者の契約に従います。
