# scripts/analysis — このプロジェクト固有の分析コード

このリポジトリ固有の分析・追試・集計スクリプトを置く。**共有ツールとは分離**する。

| 置き場 | 中身 | 同期 |
|---|---|---|
| `scripts/analysis/` | **このプロジェクト固有**の分析コード（ここ） | repo 固有・sync 対象外 |
| `scripts/research/` | PDF ingestion 等の共有パイプライン | research-template が正本・sync で配布 |

- `scripts/research/` は sync-manifest の Overwrite 管理下。
  分析コードはここ（analysis/）に置く。
- 生成物は `outputs/`（figures / tables / models、git 管理外）へ出す。
- 追試スクリプトの命名慣例: `replicate_<著者><年>.py` 等。
