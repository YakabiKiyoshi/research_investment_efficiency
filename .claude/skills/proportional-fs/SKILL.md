---
description: 連結 BS・PL・キャッシュ・フロー計算書の数値から「比例縮尺財務諸表」(各項目の高さを総資産または期間 CF 総源泉で正規化した矩形図) を MetaPost + ltjsarticle で生成するスキル。BS+PL を 1 図にまとめ s = 売上高/総資産 で総資産回転率を視覚化、CF は資金源泉 (左) / 資金使途 (右) を期間横断の同一スケールで描画する。いずれもタイトル無し (図のみ) をデフォルトとし、社名・年度は図に載せずファイル名で判別する。本体配布用 PDF と講義スライド貼り込み用の PNG を同時出力する。「比例縮尺財務諸表をつくって」「連結 BS と PL を比例縮尺で並べた図を別ケースで」のような依頼で起動する。
---

# 比例縮尺財務諸表 (Proportional-scale Financial Statements) の生成

連結 BS と PL の各項目の高さを **総資産で割った比率** で描いた矩形図、ならびに連結 CF 計算書の各活動 CF を **資金源泉 (左) / 資金使途 (右)** に振り分けて期間横断同一スケールで描いた矩形図を、MetaPost + ltjsarticle で生成するスキル。

ケース教材 (本体・ハンドアウト・ティーチング・ノート) と講義スライドで反復利用するため、テンプレート・スクリプトをコピーして年度データだけ差し替えれば動く構成にしてある。

## 起動条件

- 「比例縮尺財務諸表を○○ケースで作って」
- 「既存ケースの図を別の年度で再現して」
- 「連結 BS と PL を比例縮尺で並べた図がほしい」
- 「キャッシュ・フローを資金使途と資金源泉に分けた図を年度比較で」
- 「Keynote に貼る用のタイトル無し PNG が必要」

## 出力物

各ファイスカル・イヤー (FY) ごとに、次の 2 系統 4 ファイルが出力される。

### BS + PL 比例縮尺財務諸表

- `figs/<prefix>_proportional_fs_fy{year}.pdf` — タイトル無し (図のみ)、本体配布用
- `figs/slides/proportional_bs_pl_fy{year}.png` — タイトル無し (図のみ)、300 dpi PNG、Keynote 貼り込み用

### CF 計算書比例縮尺

- `figs/<prefix>_cf_proportional_fy{year}.pdf` — タイトル無し (図のみ)、本体配布用
- `figs/slides/proportional_cf_fy{year}.png` — タイトル無し (図のみ)、300 dpi PNG

`<prefix>` はケース略称 (例: `case1`, `caseA`)。

## 描画コンベンション

### BS + PL 図

同梱テンプレート (`build_proportional_bs_pl.py`) が出力する MetaPost を基準とする。1 ページ A4 横に次のレイアウトで配置する。

- 全体高さ `h := 145mm`、各列幅 `w := 0.34 * h`
- 横軸: `[0, w]` BS 資産側 / `[w, 2w]` BS 負債・純資産側 / 中央に空白 1w / `[3w, 4w]` PL 費用側 / `[4w, 5w]` PL 売上高
- PL ブロックの高さ = `s * h`、ここで `s = 売上高 / 総資産` = **総資産回転率**
- BS カテゴリ（資産側 6 区分 / 負債・純資産側 5 区分）:
  - 資産側: 現金預金 / 売上債権 / 棚卸資産 / 投資等（のれん等） / その他流動資産 (残差) / 固定資産
  - 負債・純資産側: 短期借入金等 / その他流動負債 (残差) / 長期借入金 / 社債・固定負債等 (残差) / 純資産
- 4 PL カテゴリ: 売上原価 / 販管費 / その他費用 (残差) / 当期純利益
- 「その他」は `1.0 - Σ(明示項目)` で計算し、合計が `1.0` ぴったりになるようにする
- **赤字 (当期純損失) の年度**: `net_income < 0` を自動判定し、当期純損失を**貸方 (右) の売上高の下**に矩形で描く。費用列 (借方=左) は売上原価・販管費・その他費用の3つだけを積み、その高さ `s + |当期純損失|/総資産` が「売上高 + 当期純損失」と一致してバランスする。費用列の極小セル (その他費用など) の外部ラベルは `emit_label(..., outside_dir="lft")` で左 (BS-PL 中央余白) に出して貸方ラベルとの衝突を避ける。黒字年度は従来どおり当期純利益を費用列の最下部に積む (挙動不変)。

### CF 計算書図

同梱テンプレート (`build_proportional_cf.py`) が出力する 2 列レイアウトを基準とする。現金 (キャッシュ) は借方項目なので、その増加であるキャッシュ・インフロー (資金源泉) を左、流出であるキャッシュ・アウトフロー (資金使途) を右に置く。

- LEFT 列 = 資金源泉 (キャッシュ・インフロー): 正の CF ＋ 資金減少 (バランス用)
- RIGHT 列 = 資金使途 (キャッシュ・アウトフロー): 負の CF (絶対値) ＋ 資金増加 (バランス用)
- 両列の高さは `max(|Σ正|, |Σ負|)` で揃え、両側を**完全にバランス**させる
- 期間横断で**単一スケール** (mm/億円) を使う。最大年度を約 115mm に合わせて自動算定 (`compute_global_scale()`)

### ラベル・フォント

- 文字は `\gtdefault` (Harano Aji Gothic) でゴシック統一
- フォントは**大・小の 2 段階のみ**を使う (`FONT_LARGE_PT=16` / `FONT_SMALL_PT=11`)。固定の `\small` / `\footnotesize` / `\scriptsize` は使わず `\fontsize{pt}{...}\selectfont` で指定する。字幅は `_em_width()` (全角=1em、半角=0.5em) で概算し、幅は列幅 `W_MM` (= `0.34*H_MM`、CF は `COL_W_MM=60`)、高さは `frac * H_MM` で評価する。レイアウトと配分は:
  - **大セル** (`>= T_TWO_LINE`、既定 7%): 2 行 `\shortstack{項目名 \\ 金額}`。大フォントが幅・高さに収まれば大、収まらなければ小に落とす (`_fits_2line()` で判定し `(FONT_LARGE_PT, FONT_SMALL_PT)` を順に試す)。
  - **中セル** (`>= T_ONE_LINE`、既定 2.5%): 1 行 (項目名 + 金額 横並び)、小フォント。
  - **小セル** (それ未満): セル外に小フォントで `label.rt` / `label.lft` + リーダー線。
- これにより、十分大きいセル (純資産・固定資産・売上高・販管費・営業 CF など) は一律 16pt の大フォント、それ以外は 11pt の小フォントになる。一番大きいセルだけが突出して大きくなることはない (「収まる限り最大」だと売上高などが過大になるため 2 段階に制限している)。サイズを変えたいときは `FONT_LARGE_PT` / `FONT_SMALL_PT` を調整する。セクション見出し (BS/PL・資金使途/源泉) は 20pt、総資産ブラケット・回転率・現金純増減キャプションは 13pt に固定。
- 大フォントで図全体が広がり A4 横では端のラベル (総資産ブラケットなど) が用紙外に出て切れることがあるため、`LATEX_HEAD` / `LATEX_HEAD_NO_TITLE` の `geometry` は広い用紙 (BS+PL は `paperwidth=560mm`、CF は `460mm`、`paperheight=320mm`) を指定する。最終的な余白は `pdfcrop` が内容に合わせて自動トリミングするので用紙サイズは大きめでよい。
- タイトル無し (図のみ) がデフォルト。PDF・PNG とも同じ `LATEX_HEAD` / `LATEX_TAIL` (`\makebox[\textwidth][c]{...図...}`) で図だけを出力し、社名・年度は図に載せない (年度は出力ファイル名で判別する)。`render_tex(d)` は社名・年度の差し替えをしない。タイトルを付けたい場合は呼び出し側で別途見出しを足す。
- 注目セル (棚卸資産、純資産、当期純利益、営業 CF など) は `\bfseries` で強調
- グレースケール塗りつぶし: `withcolor X.XXwhite` を使う (1.00 = 白、0.10 = ほぼ黒)。**重要セル** ほど暗く / 残差セルほど明るくする

### 数値の表示単位

- 「億円」を基本単位とし、`(million yen) / 100` で計算
- 兆円規模は `(million yen) / 1_000_000` で `f"{trillion:.2f}兆円"`
- 表示文字列は `\num{...}` を使わず `f"{oku:,.0f}億円"` の Python f-string で生成 (MetaPost ブロックに渡すため)

## 前提ツール

次が PATH に通っている必要がある (TeX Live 2024 標準で入る):

- `lualatex` (LuaTeX、`luamplib` で MetaPost 統合)
- `qpdf` (空白末尾ページの抽出)
- `pdfcrop` (余白の自動トリミング)
- `pdftoppm` (PDF → PNG 300 dpi 変換、PNG は Keynote 用)
- Python 3 標準ライブラリのみ (外部依存なし)

## 手順

### Step 1. テンプレートをコピー

スキルに同梱された 2 本のテンプレート・スクリプトを、対象プロジェクトの `bin/` ディレクトリにコピーする。

```bash
PROJ=/path/to/<project>
mkdir -p "$PROJ/bin" "$PROJ/figs/slides"
cp ~/.claude/skills/proportional-fs/templates/build_proportional_bs_pl.py "$PROJ/bin/"
cp ~/.claude/skills/proportional-fs/templates/build_proportional_cf.py    "$PROJ/bin/"
```

ファイル名はプロジェクトに合わせて変更してよい (例: `build_proportional_fs.py` / `build_cf_proportional_fs.py` 等)。

### Step 2. データを埋める

テンプレートの先頭にある `DATA` 辞書を、対象企業の連結財務諸表の数値で置き換える。**単位は百万円** (有価証券報告書の表示通り)。

BS + PL 用 (`build_proportional_bs_pl.py`) に必要な項目:

```python
DATA = {
    "fy2006": {                                # 任意のキー (年度識別子)
        "label_year":     "第16期 (2006年3月期)",  # 図のサブタイトル
        "total_assets":   202_990,             # 連結総資産
        "cash":            12_000,             # 現金及び預金
        "receivables":     20_323,             # 受取手形及び売掛金（売上債権）
        "inventory":       73_733,             # 棚卸資産
        "investments":     46_901,             # 投資有価証券等 (不動産投資、出資金 など)
        "fixed_assets":    37_979,             # 固定資産合計
        "current_total":   98_921,             # 流動負債合計
        "short_borrow":    59_776,             # 短期借入金 + 1年内償還社債
        "long_borrow":     26_400,             # 長期借入金
        "equity":          66_638,             # 純資産合計
        "revenue":         64_349,             # 売上高
        "cogs":            41_143,             # 売上原価
        "sga":             11_179,             # 販売費及び一般管理費
        "net_income":       7_868,             # 当期純利益
    },
    ...
}
```

CF 用 (`build_proportional_cf.py`) に必要な項目 (**単位は億円**):

```python
DATA = {
    "fy2006": {
        "label_year":   "第16期 (2006年3月期)",
        "operating_cf": -330,    # 営業活動による CF (符号付き)
        "investing_cf":  +11,    # 投資活動による CF
        "financing_cf": +430,    # 財務活動による CF
    },
    ...
}
```

スクリプトの先頭近辺にある `FILE_PREFIX` を対象企業の略称に合わせる (`COMPANY_NAME` はタイトル無しがデフォルトのため現在は図に載らない。任意)。

```python
COMPANY_NAME = "株式会社○○○○"    # 現在は図に載せない (タイトル無しがデフォルト)
FILE_PREFIX  = "abc"                  # 出力 PDF のプレフィックス (例: case1_proportional_fs_fy2006.pdf)
```

### Step 3. 強調セルの指定 (任意)

ケースのテーマに応じて、`\bfseries` 強調するセルを `BOLD_BS_ASSET` / `BOLD_BS_LE` / `BOLD_PL` 定数で切り換える。デフォルトは「棚卸資産・純資産・当期純利益」。在庫膨張がテーマの場合はそのままでよい。設備投資がテーマの場合は `BOLD_BS_ASSET = "a5"` (固定資産) に変える、など。

CF 図では `BOLD_CF_SOURCE` / `BOLD_CF_USE` で強調を変える。デフォルトは「営業 CF を強調」(資金繰り悪化型ケース向け)。

### Step 4. 実行

```bash
cd "$PROJ"
python3 bin/build_proportional_bs_pl.py
python3 bin/build_proportional_cf.py
```

各スクリプトは年度ごとに次の処理を一気通貫で実行する:

1. MetaPost コード生成
2. `lualatex` を 2 回実行 (相互参照解決)
3. `qpdf` で 1 ページ目を抽出 (空白ページ除去)
4. `pdfcrop` で図のバウンディング・ボックスにトリム
5. `figs/<prefix>_*.pdf` にコピー (タイトル無し、図のみ)
6. `pdftoppm -r 300 -png` でタイトル無し PNG を生成
7. `figs/slides/proportional_*_fy*.png` にコピー

成果物は配布資料 (本体 / TN / ハンドアウト) には PDF を、講義スライド (Beamer or Keynote) には PNG を使い分ける。

### Step 5. Makefile への組み込み (任意)

複数年度を一度に再生成するため、プロジェクトの `Makefile` に次のような行を加える。

```make
PROP_FS_PDFS = figs/<prefix>_proportional_fs_fy2006.pdf \
               figs/<prefix>_proportional_fs_fy2007.pdf \
               figs/<prefix>_proportional_fs_fy2008.pdf
PROP_FS_PNGS = figs/slides/proportional_bs_pl_fy2006.png \
               figs/slides/proportional_bs_pl_fy2007.png \
               figs/slides/proportional_bs_pl_fy2008.png

proportional_fs: $(PROP_FS_PDFS) $(PROP_FS_PNGS)

$(PROP_FS_PDFS) $(PROP_FS_PNGS): bin/build_proportional_bs_pl.py
	$(PYTHON) bin/build_proportional_bs_pl.py
```

CF 側も同様に組み込む。

### Step 6. TeX ファイルへの取込

本体・TN・ハンドアウトに比例縮尺図を埋め込むときは、A4 横ページに収めるため `pdflscape` と `subcaption` を使う。

```latex
\usepackage{pdflscape}
\usepackage{subcaption}

\begin{landscape}
\begin{figure}[ht]
\centering
\begin{subfigure}[t]{0.32\linewidth}
  \includegraphics[width=\linewidth]{figs/<prefix>_proportional_fs_fy2006.pdf}
  \caption{第16期}
\end{subfigure}\hfill
\begin{subfigure}[t]{0.32\linewidth}
  \includegraphics[width=\linewidth]{figs/<prefix>_proportional_fs_fy2007.pdf}
  \caption{第17期}
\end{subfigure}\hfill
\begin{subfigure}[t]{0.32\linewidth}
  \includegraphics[width=\linewidth]{figs/<prefix>_proportional_fs_fy2008.pdf}
  \caption{第18期}
\end{subfigure}
\caption{連結 BS と PL の比例縮尺財務諸表 (3 期分)。}
\end{figure}
\end{landscape}
```

Beamer スライドや Keynote 用には、`figs/slides/` の PNG を `\includegraphics` または Keynote のドラッグ&ドロップで貼る。

## チェックリスト

データ準備:

- [ ] `total_assets` と `(cash + receivables + inventory + investments + fixed_assets + その他)` の合計が一致するか (差は「その他流動資産」として残差扱い)
- [ ] `equity + 流動負債 + 長期借入金 + 社債・固定負債` の合計が `total_assets` と一致するか
- [ ] `s = revenue / total_assets` が 0 < s < 1.5 程度の範囲か (これを超えると PL が A4 縦に収まらない)
- [ ] 赤字年度は `net_income` を**負値**で入れる (親会社株主帰属の当期損失)。`s + |net_income|/total_assets < 1` であれば A4 に収まる (越える場合は `h` を下げる)
- [ ] CF データは `operating_cf + investing_cf + financing_cf = 現金純増減` の関係を満たすか (現金増減で完全バランスするように `compute()` 内で吸収される)

実行後:

- [ ] `figs/<prefix>_*.pdf` が **タイトル無し** (図のみ) で生成された
- [ ] `figs/slides/proportional_*_fy*.png` が **タイトル無し** で 300 dpi 生成された
- [ ] BS の左右の高さが一致している (両側とも `h` まで埋まっている)
- [ ] CF 図の左右の高さが一致している
- [ ] 「現金及び現金同等物の純増加 / 純減少」のキャプションが下部にある
- [ ] 「総資産回転率 = XX.X%」のキャプションが PL 下部にある
- [ ] 赤字年度: 当期純損失が**貸方 (右) 売上高の下**にあり、費用列 (左) の高さ = 売上高 + 当期純損失 でバランスしている

## トラブルシューティング

- `\textbf{N}` が siunitx S 列で桁区切りを失効させる → MetaPost 側では `\bfseries` で太字化する (`\textbf{}` ではなく)。本テンプレートはすでに対応済
- 図が PDF の 2 ページ目に流れる → 高さ定数 `h` を小さく (135mm → 115mm 程度)、または `geometry` の `margin` を縮める
- PNG が薄い / 色ムラ → `pdftoppm -r 300` を `-r 400` に上げる (ファイル・サイズも大きくなる)
- Keynote で貼ると周囲に白枠が残る → `pdfcrop` の `--margins 0` 指定。本テンプレートはデフォルトで `pdfcrop` をかけているので通常は問題ないはず
- 日本語が豆腐化 → `\renewcommand{\kanjifamilydefault}{\gtdefault}` が `LATEX_HEAD` にあるか確認。Harano Aji Gothic が入っていない環境では `\renewcommand{\familydefault}{\sfdefault}` を `\rmdefault` に戻す

## 関連ファイル

- `~/.claude/skills/proportional-fs/templates/build_proportional_bs_pl.py` — BS+PL テンプレート
- `~/.claude/skills/proportional-fs/templates/build_proportional_cf.py` — CF テンプレート

## 関連スキル

- `commit-push` — 図の生成・取込が完了したらコミット・プッシュに引き継ぐ
- `save-progress` — 新規ケースでテンプレートを採用した際に、項目分類やハイライト方針の判断を memory に残す
