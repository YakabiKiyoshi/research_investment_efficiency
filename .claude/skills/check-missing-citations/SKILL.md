---
description: 論文（LaTeX .tex / .bib）が引用する文献が、PDFリポジトリ（../papers/[A-Z] 等、著者姓を「_」で繋ぎ「_刊行年_誌略称.pdf」で命名）に実在するか照合し、欠落文献を doc/missing_citations.csv に保存する。第1列=ジャーナル名、第2列=論文タイトル。CSVはUTF-8 BOM付きで文字化けを防ぐ。
---

# 引用文献の所在チェック（欠落文献リストの作成）

論文の本文（`.tex`）が引用する全文献を抽出し、それぞれが論文 PDF リポジトリ
（`../papers/[A-Z]` 等、ファイル名が `著者姓_..._著者姓_刊行年_誌略称.pdf` 規則）に
実在するかを照合する。リポジトリに**存在しない**文献を `doc/missing_citations.csv` に保存する。

このスキルはメイン会話で直接実行してよい（軽量・短時間）。Agent への委譲は不要。

## 引数

- `$ARGUMENTS`（省略可）: 照合対象の `.tex` ファイル（スペース区切りで複数指定可、相対／絶対パス）。
- 省略時は cwd 直下の `*.tex` を対象にする（複数あって対象が曖昧ならユーザーに確認）。
- PDF リポジトリの場所は既定で `<cwd>/../papers`。`.claude/citation_check.md` / `.claude/proofread.md` に
  「文献探索ディレクトリ」の記載があればそれを優先する。

## 絶対の制約

- **対象の .tex / .bib は絶対に編集しない**。出力は `doc/missing_citations.csv` のみ。
- 推測でファイルの存在を判定しない。実ファイルの有無で判定する。
- CSV は **UTF-8（BOM 付き）** で書き出す。日本語を含む場合の Excel での文字化けを防ぐため。

## 文献命名規則（リポジトリ側）

PDF ファイル名と bib キーは同一規則：
- 著者の姓を最終著者まで順にアンダーバーで繋ぐ → `_刊行年_誌略称`
- 例: `Dechow_Sloan_Sweeney_1995_TAR.pdf`, `Demski_1974_TAR.pdf`, `Avenhaus_vonStengel_Zamir_2002_HGT.pdf`
- リポジトリは頭文字でフォルダ分け: `papers/<最初の1文字>/<キー>.pdf`
- 日本語訳併存の場合 `<キー>.jp.pdf` / `<キー>.jp.tex` がある。本体存在の判定には `.pdf` / `.jp.pdf` のいずれかがあれば「存在」とみなす。
- 姓内部表記のゆらぎ（`vonStengel` ↔ `von_Stengel` 等）に注意。緩めに照合する。

## 手順

### Step 1. 対象ファイルと探索ディレクトリの決定

1. `$ARGUMENTS` があれば対象 `.tex` とする。なければ cwd 直下の `*.tex`。
2. PDF リポジトリは `<cwd>/../papers`（既定）。`.claude/citation_check.md` / `.claude/proofread.md` に
   探索ディレクトリ指定があれば上書き。
3. 同ディレクトリに `.bib` があれば、ジャーナル名・タイトル・著者・刊行年・エントリ種別の取得元として読む。

### Step 2. 引用キーの抽出

対象 `.tex` から全 `\cite` 系コマンドのキーを抽出（重複削除）：

```bash
grep -hoE '\\(cite|citep|citet|citetalias|citepalias|citeauthor|citealp|citealt|nocite)[a-z]*\*?(\[[^]]*\])?\{[^}]+\}' *.tex \
  | grep -oE '\{[^}]+\}' | tr -d '{}' | tr ',' '\n' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sort -u
```

### Step 3. リポジトリでの存在照合

各キー `k` について、頭文字フォルダ `papers/<k の1文字目>/` 内に
`k.pdf` / `k.jp.pdf`（および `vonStengel`→`von_Stengel` 等の表記ゆらぎ版）が
あるかを実ファイルで確認する。

**重要（zsh の落とし穴）**: このセッションのシェルは zsh。`for k in $keys`（裸の変数）は
**単語分割されず 1 反復で終わる**。かならず `while IFS= read -r k` で行ごとに回すこと：

```bash
cd <repo_parent>   # papers/ の親
grep -hoE '\\(cite|citep|citet|citetalias|citepalias|citeauthor|citealp|citealt|nocite)[a-z]*\*?(\[[^]]*\])?\{[^}]+\}' <tex_dir>/*.tex \
  | grep -oE '\{[^}]+\}' | tr -d '{}' | tr ',' '\n' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sort -u \
  | while IFS= read -r k; do
      [ -z "$k" ] && continue
      L=$(printf '%s' "$k" | cut -c1)
      alt=$(printf '%s' "$k" | sed 's/vonStengel/von_Stengel/')
      if [ -f "papers/$L/$k.pdf" ] || [ -f "papers/$L/$k.jp.pdf" ] \
         || [ -f "papers/$L/$alt.pdf" ] || [ -f "papers/$L/$alt.jp.pdf" ]; then
        st=FOUND
      else
        st=MISSING
      fi
      printf '%-8s %s\n' "$st" "$k"
    done
```

頭文字フォルダで見つからない場合は、誌略称のゆらぎ（`_RJE`↔`_RAND`, `_TAR`↔`_AcctRev` 等）や
著者・年が一致する近傍候補を `ls papers/<L>/` で目視確認してから MISSING と確定する。

### Step 4. 欠落文献のメタデータ収集

MISSING の各キーについて、`.bib` から以下を取得（`.bib` が無ければキー名から推定し、不明は空欄）：
- ジャーナル名（`journal` / `booktitle` / `institution` / `publisher`。フルネームで書く）
- タイトル（`title`）
- 著者（`author`）
- 刊行年（`year`）
- エントリ種別（`@article` / `@book` / `@techreport` / `@unpublished` 等）

### Step 5. CSV の書き出し

`<cwd>/doc/missing_citations.csv` に保存（`doc/` が無ければ作成）。

- **第1列 = ジャーナル名、第2列 = 論文タイトル**（指定の固定列）。第3列以降は任意：
  推奨は `bibkey, authors, year, entry_type`。
- **UTF-8 BOM** を先頭に付ける（`printf '\xEF\xBB\xBF'`）。
- カンマ・コロン・引用符を含むフィールドは `"..."` で囲む（タイトルはほぼ確実に該当）。
- 欠落が 0 件なら、ヘッダ行のみの CSV を書き、その旨を報告する。

```bash
printf '\xEF\xBB\xBF' > doc/missing_citations.csv
printf 'journal,title,bibkey,authors,year,entry_type\n' >> doc/missing_citations.csv
# 各 MISSING 行を、必要に応じて "..." で quote して追記
```

### Step 6. ユーザーへの報告

- 引用キー総数、FOUND 件数、MISSING 件数
- 出力ファイルの絶対パス
- MISSING の一覧（キー名）を簡潔に

## 検証チェックリスト

- [ ] zsh で `while read` を使い、全キーを反復したか（`for k in $keys` を避けたか）
- [ ] `.jp.pdf` のみ存在するものを「存在」と正しく扱ったか
- [ ] 表記ゆらぎ（vonStengel 等）で取りこぼしていないか
- [ ] CSV に BOM を付けたか、タイトルを quote したか
- [ ] 第1列ジャーナル名・第2列タイトルの順を守ったか
- [ ] 欠落 0 件のときもヘッダのみの CSV を出力したか

## 関連スキル

- `citation-check`: 入手済み文献の**内容**と本文主張の整合を検証（本スキルは所在の有無のみ）。
- `rename-papers` / `sort-papers`: PDF リポジトリのファイル名規則・フォルダ整理。
- `commit-push`: 生成した CSV のコミット（ユーザー明示時のみ）。
