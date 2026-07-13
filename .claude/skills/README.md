# Claude Code スキル集

学術論文（LaTeX）の執筆・校正・文献管理、および財務図表の生成を支援する
Claude Code 用のカスタム・スキル集です。各スキルは 1 つのディレクトリにまとまっており、
`SKILL.md`（指示書）と、必要に応じて補助スクリプト（`templates/`）から構成されます。

このディレクトリを丸ごと共有して使うことを想定しています。スキル内のパスはすべて
`~/`（ホーム相対）またはプレースホルダ（`/path/to/...`、`<project>` 等）に一般化してあります。
各自の環境に合わせて読み替えてください。

## 前提

- **Claude Code**（CLI / VSCode 拡張 / デスクトップ・アプリのいずれか）。スキルはここから起動します。
- **proportional-fs のみ**追加の外部ツールが必要です（他のスキルは Claude Code だけで動きます）:
  - `lualatex`（LuaTeX。`luamplib` で MetaPost を統合）
  - `pdfcrop`（余白の自動トリミング）
  - `pdftoppm`（PDF → PNG 300 dpi 変換。スライド貼り込み用）
  - Python 3（標準ライブラリのみ。外部パッケージ不要）
  - Harano Aji Gothic フォント（日本語ゴシック。無い環境では `SKILL.md` の注記に従い代替設定）

## インストール

スキルは「ディレクトリごと」`~/.claude/skills/` 配下に置けば認識されます。

```sh
# このリポジトリの skills/ から、自分の Claude Code スキル・ディレクトリへコピー
mkdir -p ~/.claude/skills
cp -R skills/* ~/.claude/skills/
```

- 全ユーザー共通で使うなら `~/.claude/skills/`（上記）。
- 特定プロジェクトだけで使うなら、そのプロジェクト直下の `.claude/skills/` に置く。
- インストール後、Claude Code を再起動するか新しいセッションを開くと一覧に現れます。
- 確認: セッションで `/` を入力するとスキル名が補完候補に出ます。

## 起動のしかた

2 通りあります。

1. **スラッシュ・コマンド**: 会話で `/<スキル名>` と打つ（例: `/proofread-paper`、`/commit-push`）。
   引数を取るスキルは `/<スキル名> 対象ファイル.tex` のように続けて渡せます。
2. **自然言語**: 依頼文がスキルの用途に合致すると自動的に起動します
   （例:「この論文を校正して」「Github にコミットしてプッシュ」「引用が文献に整合的か確認して」）。

## スキル一覧

### 論文の検証・校正

| スキル | 用途 | 出力 |
|---|---|---|
| `proofread-paper` | 日本語論文（LaTeX）の徹底校正。文章表現・数学記法・数値・引用・LaTeX 形式を検査 | `doc/proof_reading_X.txt` |
| `math-proof-check` | 証明・命題・数値計算・参照整合性など数学的厳密性を検証 | `doc/math_proof_check_X.txt` |
| `overclaim-check` | 主張が証明・実証結果の範囲を超えていないか（overclaim）を検証 | `doc/overclaim_report_X.txt` |
| `citation-check` | 引用文献を実際に読み、本文の引用・要約が文献内容と整合するか検証 | `doc/citation_check_X.txt` |
| `check-missing-citations` | 引用文献が PDF リポジトリに実在するか照合し、欠落を抽出 | `doc/missing_citations.csv` |

これらは原稿（`.tex`）を**直接編集せず**、結果ファイルに保存するのみです。`proofread-paper` /
`math-proof-check` / `overclaim-check` はバックグラウンドで実行され、メイン会話をブロックしません。

対象ファイルの指定方法（4 スキル共通）:

- 引数で `.tex` を渡す、または
- プロジェクト直下に `.claude/proofread.md` を置き、そこに対象ファイルと既知情報
  （プロジェクト固有の数値・追加ルール等）を記載しておくと自動で読み込まれます。

### 論文の編集・記法

| スキル | 用途 |
|---|---|
| `notation-refactor` | 数学記号・呼称・添字のリネーム／統一／宣言追加を、影響調査から再タイプセット検証まで一貫実施 |
| `translate-paper` | 学術論文 PDF を日本語に全訳し LaTeX 出力 |

### 文献ファイル管理

| スキル | 用途 |
|---|---|
| `rename-papers` | PDF 論文を「著者姓_発行年_誌略称.pdf」へ一括リネーム（既定の作業先 `~/papers/work/`） |
| `sort-papers` | PDF を頭文字で `papers/A-Z` フォルダへ振り分け（同名既存は古い方を残す） |

`rename-papers` / `sort-papers` の作業ディレクトリ（既定 `~/papers/...`）は、各自の論文 PDF
リポジトリの場所に合わせて読み替えてください。

### 図表生成

| スキル | 用途 |
|---|---|
| `proportional-fs` | 連結 BS・PL・CF から比例縮尺財務諸表（MetaPost）を生成。配布用 PDF と講義用 PNG を同時出力 |

使い方: `templates/` の Python スクリプトを対象プロジェクトの `bin/` にコピーし、スクリプト内の
`DATA` 辞書に財務数値を入れて実行します。詳細は `proportional-fs/SKILL.md` を参照。
前提ツール（`lualatex` 等）は上の「前提」を満たしておく必要があります。

### 運用・セッション

| スキル | 用途 |
|---|---|
| `commit-push` | 変更を単一コミットにまとめ origin の同名ブランチへプッシュ（`git add .` を避け個別指定） |
| `save-progress` | 会話セッションの非自明な経緯を Claude の user memory に整理保存し索引を更新 |

### PDF ingestion

| スキル | 用途 |
|---|---|
| `pdf-ingestion` | 論文 PDF を決定論的パイプラインでアーティファクト化し query packet で消費（要 `scripts/research/pdf_*.py`） |

`pdf-ingestion` は repo 側の `scripts/research/` を前提とするため、
**プロジェクト直下の `.claude/skills/` に置いて使う**（research-template から同期される）。

## カスタマイズ

- 各スキルの挙動は `<スキル名>/SKILL.md` を編集すれば変えられます。
- 出力先・既定パス・用語ルール等もすべて `SKILL.md` 内に書かれています。
- 論文校正系を使うプロジェクトでは、`.claude/proofread.md` にプロジェクト固有の
  既知数値・優先事項を書いておくと検証の精度が上がります。
