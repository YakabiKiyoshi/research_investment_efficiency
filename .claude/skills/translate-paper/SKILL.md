# 学術論文PDF日本語全訳（LaTeX出力）

指定されたPDFファイルの学術論文を日本語に全訳し、LaTeXソースとして出力するスキルです。

## 引数

$ARGUMENTS にPDFファイルのパスが渡されます。

## 手順

以下の手順を**確認を求めず一気に**実行してください。

### 1. PDFテキスト抽出

```
pdftotext "$ARGUMENTS" /tmp/translate_paper_full.txt
```

で全文を抽出する。抽出されたテキストを全て読み込む。

### 2. 論文情報の特定

抽出テキストの冒頭から以下を特定する：
- タイトル
- 著者名・所属
- 掲載誌名、巻号、ページ、出版年
- セクション構成（節・小節の番号とタイトル）
- 脚注の数

### 3. 出力ファイルパスの決定

- 入力PDFと同じディレクトリに出力する
- ファイル名は入力PDFの `.pdf` を `.jp.tex` に置換したものとする
- 例: `Jensen_Meckling_1976_JFE.pdf` → `Jensen_Meckling_1976_JFE.jp.tex`

### 4. 全訳LaTeXファイルの作成

以下の要件を厳守して日本語訳LaTeXファイルを作成する：

#### ドキュメントクラスとパッケージ
```latex
\documentclass[a4paper,11pt]{ltjsarticle}
\usepackage{amsmath,amssymb,amsthm}
\usepackage[margin=25mm]{geometry}
\usepackage{enumitem}
```

#### 翻訳の要件（最重要）

- **全訳（完訳）であること。抄訳は不可。**
- 原論文のすべての節（section）、小節（subsection）、段落を漏れなく翻訳する
- すべての脚注を `\footnote{}` として翻訳する
- すべての数式を原文通りに再現する
- 図の説明文（Figure caption）は `\paragraph{図N}` として翻訳する
- 定理・命題・証明はすべて翻訳する
- 参考文献リストは `\begin{thebibliography}` で全件収録する（著者名・タイトルは原語のまま）
- `\citeauthor` や `\citep` 等のnatbibコマンドは使用しない。本文中の引用は「Jensen and Meckling (1976)」のようにインラインで記述する

#### タイトルページ

```latex
\title{{\Large 日本語タイトル}\thanks{著者脚注の翻訳}}
\author{原著者名（ローマ字のまま）\\所属の翻訳\\
{\small 原論文情報}\\
{\small （日本語全訳）}}
\date{}
```

#### 翻訳の品質基準

- 学術的に正確な日本語を使用する
- 専門用語は定訳がある場合はそれに従う（例: agency costs → エージェンシー・コスト）
- 原文の論理構造と議論の流れを忠実に再現する
- 冗長な意訳は避け、原文に忠実な逐語訳を基本とする

### 5. コンパイルと検証

作成したLaTeXファイルを以下でコンパイルする：

```
cd (出力ファイルのディレクトリ) && lualatex (ファイル名)
```

- エラーが出た場合は修正して再コンパイルする
- 成功したらページ数を報告する

### 6. TeX生成ファイルのクリーンアップ

コンパイル成功後、`.jp.tex` と `.jp.pdf` 以外のTeX関連生成ファイルを削除する。
具体的には、出力ファイルのベース名（拡張子なし）に対して以下の拡張子のファイルを削除する：

```
.aux .log .out .toc .lof .lot .fls .fdb_latexmk .synctex.gz .nav .snm .vrb .bbl .blg .idx .ilg .ind .ist
```

例: `Jensen_Meckling_1976_JFE.jp.tex` を出力した場合、
`Jensen_Meckling_1976_JFE.jp.aux`、`Jensen_Meckling_1976_JFE.jp.log` 等を削除する。

```bash
cd (出力ファイルのディレクトリ) && rm -f (ベース名).jp.aux (ベース名).jp.log (ベース名).jp.out (ベース名).jp.toc (ベース名).jp.lof (ベース名).jp.lot (ベース名).jp.fls (ベース名).jp.fdb_latexmk (ベース名).jp.synctex.gz (ベース名).jp.nav (ベース名).jp.snm (ベース名).jp.vrb (ベース名).jp.bbl (ベース名).jp.blg (ベース名).jp.idx (ベース名).jp.ilg (ベース名).jp.ind (ベース名).jp.ist
```

最終的にディレクトリには `.jp.tex` と `.jp.pdf` のみが残る状態にする。

### 7. 完了報告

以下を報告する：
- 出力ファイルのパス（.jp.tex と .jp.pdf）
- PDFのページ数
- 翻訳した節の数
- 翻訳した脚注の数
- 参考文献の件数
