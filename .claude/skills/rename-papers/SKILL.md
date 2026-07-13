---
name: rename-papers
description: workディレクトリ以下のPDF論文を著者last name・発行年・ジャーナル略称でリネームするスキル。例: Dechow_Sloan_Sweeney_1995_TAR.pdf
---

# 論文PDFリネーム・スキル

`~/papers/work/` 以下にあるすべてのPDFを順に読み、著者のlast names・発行年・ジャーナル名を取り出し、

```
LastName1_LastName2_..._LastNameN_Year_JournalAbbrev.pdf
```

の形式にリネームします。

## 手順

以下を**確認を求めず一気に**実行する。

### 1. workディレクトリ内のPDFを列挙

```
ls ~/papers/work/*.pdf
```

### 2. 各PDFの1ページ目を読む

Readツールで `pages: "1"` を指定して1ページ目を取得する。JSTORのカバーページがある場合はそこに全情報（著者、ジャーナル、巻号、年、ページ）が記載されている。カバーページがない場合は通常の1ページ目にタイトル・著者・ジャーナル情報がある。

### 3. 情報抽出

各論文から以下を抽出する：

- **著者のlast names**: 論文記載順（アルファベット順ではない）。例: "Renée B. Adams and Daniel Ferreira" → `Adams`, `Ferreira`
- **発行年**: 4桁西暦
- **ジャーナル名**: フルネームを識別

### 4. ジャーナル略称への変換

以下の対応表に基づき略称を決定する。表にないジャーナルは、一般的な学術略称（頭字語）を使用する。迷う場合はユーザーに確認せず、頭文字（The, of, and, Journal of 等の冠詞・前置詞・Journalを除く）から合理的な略称を作る。

| フルネーム | 略称 |
|---|---|
| The Accounting Review | TAR |
| Journal of Accounting Research | JAR |
| Journal of Accounting and Economics | JAE |
| Review of Accounting Studies | RAST |
| Contemporary Accounting Research | CAR |
| Accounting, Organizations and Society | AOS |
| Journal of Finance / The Journal of Finance | JF |
| Journal of Financial Economics | JFE |
| Review of Financial Studies / The Review of Financial Studies | RFS |
| Journal of Corporate Finance | JCF |
| Journal of Financial and Quantitative Analysis | JFQA |
| Journal of Banking and Finance | JBF |
| American Economic Review / The American Economic Review | AER |
| Journal of Political Economy | JPE |
| Quarterly Journal of Economics / The Quarterly Journal of Economics | QJE |
| Review of Economic Studies / The Review of Economic Studies | RES |
| Econometrica | ECTA |
| RAND Journal of Economics / The RAND Journal of Economics | RAND |
| Bell Journal of Economics / The Bell Journal of Economics | BJE |
| Journal of Economic Theory | JET |
| Journal of Economic Literature | JEL |
| Journal of Economic Perspectives | JEP |
| Journal of Law and Economics | JLE |
| Journal of Law, Economics, and Organization | JLEO |
| Journal of Business / The Journal of Business | JB |
| Management Science | MS |
| Review of Economics and Statistics / The Review of Economics and Statistics | REStat |
| International Economic Review | IER |
| Games and Economic Behavior | GEB |

### 5. ファイル名生成

著者last nameをアンダースコアで連結し、年とジャーナル略称をアンダースコアで繋ぐ。

例:
- Dechow, Sloan, Sweeney, 1995, The Accounting Review → `Dechow_Sloan_Sweeney_1995_TAR.pdf`
- Hermalin and Weisbach, 1998, American Economic Review → `Hermalin_Weisbach_1998_AER.pdf`
- Demski, 1974, The Accounting Review → `Demski_1974_TAR.pdf`

last name中のハイフン・アポストロフィ・スペースは保持する（例: `O'Brien`, `García-Feijoo`）。ただし、ファイル名に問題が生じる文字（`/`, `:`等）は避け、アクセント記号は可能なかぎり保持する。

### 6. リネーム実行

`mv` コマンドで一括リネームする。複数の `mv` を `&&` で繋げて1つのBashコマンドにまとめる。

```
cd ~/papers/work/ && mv "old1.pdf" "New_Name1.pdf" && mv "old2.pdf" "New_Name2.pdf" && ls
```

最後に `ls` で結果を確認する。

### 7. 報告

リネーム対象すべてを新旧対応で簡潔に一覧報告する。

## 注意

- PDFを読むのはすべて1ページ目のみ。2ページ目以降は不要。
- 著者名の順序は論文記載順を維持する（アルファベット順に並び替えない）。
- 複合姓（von, van, de, del, della等）は通常 last name の一部として扱う。例: "van der Berg" → `vanderBerg` もしくは `van_der_Berg` ではなく、慣用的な表記に従う（通常は `vanderBerg` ではなく `VanDerBerg` 等、姓全体を1語として扱う）。判断が難しい場合はスペースをそのまま保持せず詰める。
- ジャーナルが表になく特定困難な場合でも、ユーザーに確認を求めず合理的な略称で進める。
