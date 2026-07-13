#!/usr/bin/env python3
"""連結 BS + PL の比例縮尺財務諸表 (proportional-scale BS+PL chart) を生成する。

各 BS 項目と PL 項目の高さを連結総資産で正規化した矩形図を、年度ごとに
A4 横 1 ページに描画する。PL ブロックの高さ s = 売上高 / 総資産 が
総資産回転率を視覚化する。出力は次の 2 系統:

  figs/<FILE_PREFIX>_proportional_fs_<key>.pdf       (タイトル無し、配布用)
  figs/slides/proportional_bs_pl_<key>.png            (タイトル無し、Keynote 用、300 dpi)

スキル本体: ~/.claude/skills/proportional-fs/SKILL.md

使い方: 下の DATA 辞書、FILE_PREFIX、BOLD_* を埋めて (COMPANY_NAME は任意)
        python3 bin/build_proportional_bs_pl.py を実行。
"""

from pathlib import Path
import subprocess
import shutil
import tempfile

# === プロジェクト固有設定 (要編集) =======================================

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "figs"

COMPANY_NAME = "株式会社○○○○"            # 現在は図に載せない (タイトル無しがデフォルト)
FILE_PREFIX  = "abc"                          # 出力 PDF のプレフィックス

# 強調セルの key (\bfseries で太字化)
BOLD_BS_ASSET = "a3"     # a1〜a6 のいずれか or None。デフォルトは棚卸資産
BOLD_BS_LE    = "k1"     # l1〜l4, k1。デフォルトは純資産
BOLD_PL       = "e4"     # e1〜e4。デフォルトは当期純利益

# 連結 BS/PL の数値 (単位: 百万円)。年度ごとに辞書を追加していく。
# 資産側は 現金預金 / 売上債権 / 棚卸資産 / 投資等 / その他流動資産(残差) / 固定資産 の 6 区分。
DATA = {
    "fy2006": {
        "label_year":   "第16期 (2006年3月期)",
        "total_assets": 202_990,
        "cash":          12_000,    # 現金及び預金
        "receivables":   20_323,    # 受取手形及び売掛金（売上債権）
        "inventory":     73_733,
        "investments":   46_901,    # 投資有価証券等
        "fixed_assets":  37_979,
        "current_total": 98_921,    # 流動負債合計
        "short_borrow":  59_776,    # 短期借入金 + 1 年内償還社債
        "long_borrow":   26_400,
        "equity":        66_638,    # 純資産合計
        "revenue":       64_349,
        "cogs":          41_143,
        "sga":           11_179,
        "net_income":     7_868,
    },
    # "fy2007": {...},
    # "fy2008": {...},
}

# === 描画コンベンション (通常は編集不要) =================================

# グレースケール塗りつぶしの濃淡 (1.00 = 白、0.10 = ほぼ黒)
SHADE = {
    "a1": 0.95,  # 現金預金
    "a2": 0.88,  # 売上債権
    "a3": 0.78,  # 棚卸資産 (強調)
    "a4": 0.86,  # 投資等
    "a5": 0.97,  # その他流動資産
    "a6": 0.82,  # 固定資産
    "l1": 0.80,  # 短期借入金等
    "l2": 0.93,  # その他流動負債
    "l3": 0.72,  # 長期借入金
    "l4": 0.86,  # 社債・固定負債等
    "k1": 1.00,  # 純資産 (白)
    "e1": 0.86,  # 売上原価
    "e2": 0.93,  # 販管費
    "e3": 0.96,  # その他費用
    "e4": 0.68,  # 当期純利益 (強調)
    "rev": 0.95, # 売上高
}

# ラベル・サイズ閾値 (セル高さ / 図全体高さ h)
T_TWO_LINE = 0.07    # >= 7%: 2 行 (項目名 + 金額)、収まる限り最大フォント
T_ONE_LINE = 0.025   # >= 2.5%: 1 行、収まる限り最大フォント
# < 2.5%: セル外にラベル + リーダー線

# 図の物理寸法 (build_metapost の h, w と一致させること)。フォント自動配分に使う。
H_MM = 145.0
W_MM = 0.34 * H_MM           # BS/PL 各列の幅 (mm)
PT2MM = 0.3528               # 1pt ≈ 0.3528mm
# フォントは大・小の 2 段階のみを使う。大きいセルは大、収まらないセルは小に落とす。
FONT_LARGE_PT = 16           # 大: 十分大きいセル
FONT_SMALL_PT = 11           # 小: 中位・小セル / セル外ラベル

# 項目ラベル (順序固定)。プロジェクトによって名称を変えてもよい。
ASSET_NAMES = [
    ("a1", "現金預金"),
    ("a2", "売上債権"),
    ("a3", "棚卸資産"),
    ("a4", "投資等"),
    ("a5", "その他流動資産"),
    ("a6", "固定資産"),
]
LE_NAMES = [
    ("l1", "短期借入金等"),
    ("l2", "その他流動負債"),
    ("l3", "長期借入金"),
    ("l4", "社債・固定負債等"),
    ("k1", "純資産"),
]
PL_NAMES = [
    ("e1", "売上原価"),
    ("e2", "販管費"),
    ("e3", "その他費用"),
    ("e4", "当期純利益"),
]


# === ロジック (通常は編集不要) ===========================================

def yen_label(amount_million):
    oku = amount_million / 100.0
    if abs(oku) >= 10000:
        return f"{oku/10000:.2f}兆円"
    return f"{oku:,.0f}億円"


def compute(d):
    T = d["total_assets"]
    a1 = d["cash"] / T
    a2 = d["receivables"] / T
    a3 = d["inventory"] / T
    a4 = d["investments"] / T
    a6 = d["fixed_assets"] / T
    a5 = 1.0 - a1 - a2 - a3 - a4 - a6   # 残差 = その他流動資産

    l1 = d["short_borrow"] / T
    l2 = (d["current_total"] - d["short_borrow"]) / T
    l3 = d["long_borrow"] / T
    k1 = d["equity"] / T
    l4 = 1.0 - l1 - l2 - l3 - k1       # 残差 = 社債・固定負債等

    R = d["revenue"]
    s = R / T
    e1 = d["cogs"] / T
    e2 = d["sga"] / T
    e4 = d["net_income"] / T
    e3 = s - e1 - e2 - e4              # 残差 = その他費用

    return locals()


def emit_fill(xl, xr, yt, yb, shade):
    return (
        f"  fill ({xl}, {yb})--({xr}, {yb})--({xr}, {yt})--({xl}, {yt})--cycle\n"
        f"       withcolor {shade}white;\n"
    )


def _sizecmd(pt):
    """指定 pt の \\fontsize コマンド (行送りは 1.16 倍)。"""
    return f"\\fontsize{{{pt}}}{{{pt * 1.16:.1f}}}\\selectfont "


def _em_width(s):
    """文字列の概算字幅 (全角 = 1em、半角 = 0.5em)。"""
    return sum(1.0 if ord(ch) >= 0x2E80 else 0.5 for ch in s)


def _fits_2line(name, amount, pt, wc_mm, hc_mm):
    """項目名と金額を 2 行で積んだとき、指定 pt がセル幅・高さに収まるか。"""
    max_em = max(_em_width(name), _em_width(amount))
    w = max_em * pt * PT2MM
    h = 2 * 1.22 * pt * PT2MM
    return w <= 0.86 * wc_mm and h <= 0.82 * hc_mm


def emit_label(name, amount, frac, x_center, y_center, outside_x=None,
               bold=False, leader_inner_x=None, outside_dir="rt",
               cell_w_mm=W_MM):
    """大・小 2 段階のフォントでラベルを置く。

    十分高いセルは 2 行 (項目名 / 金額)。大フォントが幅・高さに収まれば大、
    収まらなければ小に落とす。中位のセルは 1 行 (小)、極小セルはセル外に
    リーダー線付き (小)。使うフォントは FONT_LARGE_PT と FONT_SMALL_PT の 2 種のみ。
    """
    bo = "\\bfseries " if bold else ""
    hc = frac * H_MM
    wc = cell_w_mm
    if frac >= T_TWO_LINE:
        for pt in (FONT_LARGE_PT, FONT_SMALL_PT):
            if _fits_2line(name, amount, pt, wc, hc):
                body = f"{_sizecmd(pt)}{bo}\\shortstack{{{name}\\\\{amount}}}"
                return f"  label(btex {body} etex, ({x_center}, {y_center}));\n"
    if frac >= T_ONE_LINE:
        body = f"{_sizecmd(FONT_SMALL_PT)}{bo}{name} {amount}"
        return f"  label(btex {body} etex, ({x_center}, {y_center}));\n"
    # 極小セル: セル外にリーダー線付き (margin に置くので幅制約なし、小フォント)
    # outside_dir="rt": 右に外出し / "lft": 左に外出し (費用列の極小セル向け)
    body = f"{_sizecmd(FONT_SMALL_PT)}{bo}{name} {amount}"
    pos = "label.rt" if outside_dir == "rt" else "label.lft"
    return (
        f"  {pos}(btex {body} etex, ({outside_x}, {y_center}));\n"
        f"  draw ({leader_inner_x}, {y_center})--({outside_x}, {y_center});\n"
    )


def _bs_box(side, top_frac, bot_frac):
    if side == "asset":
        xl, xr = "0", "w"
    else:
        xl, xr = "w", "2w"
    yt = f"(1 - {top_frac:.5f})*h"
    yb = f"(1 - {bot_frac:.5f})*h" if bot_frac < 1.0 else "0"
    return xl, xr, yt, yb


def build_metapost(d, c):
    T = d["total_assets"]
    out = []
    add = out.append

    add("beginfig(1);\n")
    add("  numeric h, w, s;\n")
    add("  h := 145mm;\n")
    add("  w := 0.34 * h;\n")
    add(f"  s := {c['s']:.5f};\n\n")

    # データの amount マップ
    asset_amounts = {
        "a1": d["cash"],       "a2": d["receivables"], "a3": d["inventory"],
        "a4": d["investments"], "a5": c["a5"] * T,      "a6": d["fixed_assets"],
    }
    le_amounts = {
        "l1": d["short_borrow"], "l2": c["l2"] * T,
        "l3": d["long_borrow"],  "l4": c["l4"] * T,
        "k1": d["equity"],
    }
    pl_amounts = {
        "e1": d["cogs"], "e2": d["sga"],
        "e3": c["e3"] * T, "e4": d["net_income"],
    }

    asset_cells = [(k, c[k], n, yen_label(asset_amounts[k]))
                   for k, n in ASSET_NAMES]
    le_cells    = [(k, c[k], n, yen_label(le_amounts[k]))
                   for k, n in LE_NAMES]
    pl_cells    = [(k, c[k], n, yen_label(pl_amounts[k]), (k == BOLD_PL))
                   for k, n in PL_NAMES]

    # --- 資産側 fill ---
    cum = 0.0
    asset_centers = []
    for i, (key, frac, name, amt) in enumerate(asset_cells):
        top = cum
        bot = cum + frac if i < len(asset_cells) - 1 else 1.0
        xl, xr, yt, yb = _bs_box("asset", top, bot)
        add(emit_fill(xl, xr, yt, yb, SHADE[key]))
        center_y = f"(1 - {top + 0.5 * frac:.5f})*h"
        asset_centers.append((key, frac, name, amt, center_y))
        cum += frac

    # L+E fill
    cum = 0.0
    le_centers = []
    for i, (key, frac, name, amt) in enumerate(le_cells):
        top = cum
        bot = cum + frac if i < len(le_cells) - 1 else 1.0
        xl, xr, yt, yb = _bs_box("le", top, bot)
        add(emit_fill(xl, xr, yt, yb, SHADE[key]))
        center_y = f"(1 - {top + 0.5 * frac:.5f})*h"
        le_centers.append((key, frac, name, amt, center_y))
        cum += frac

    # 赤字 (当期純損失) の判定。赤字時は当期純損失を貸方 (右) 売上高の下に描く。
    is_loss = c["e4"] < 0
    loss_frac = -c["e4"] if is_loss else 0.0
    pl_total = c["s"] + loss_frac        # 費用列・(売上高+当期純損失)列の総高さ

    # PL 売上高 (右半分 [4w, 5w])
    add(emit_fill("4w", "5w", "h", f"(1-{c['s']:.5f})*h", SHADE["rev"]))
    # 当期純損失 (売上高の下、右半分)
    if is_loss:
        add(emit_fill("4w", "5w", f"(1-{c['s']:.5f})*h",
                      f"(1-{pl_total:.5f})*h", SHADE["e4"]))

    # PL 費用 (左半分 [3w, 4w])。赤字時は e4 を費用列から外し、e1,e2,e3 のみ積む
    # (e1+e2+e3 = s + loss_frac となり、貸方の 売上高+当期純損失 と高さが一致する)。
    if is_loss:
        cost_cells = [(k, c[k], n, yen_label(pl_amounts[k]), False)
                      for k, n in PL_NAMES if k != "e4"]
    else:
        cost_cells = pl_cells
    cum = 0.0
    pl_centers = []
    for (key, frac, name, amt, bold) in cost_cells:
        top = cum
        bot = cum + frac
        yt = f"(1 - {top:.5f})*h"
        yb = f"(1 - {bot:.5f})*h"
        add(emit_fill("3w", "4w", yt, yb, SHADE[key]))
        center_y = f"(1 - {top + 0.5 * frac:.5f})*h"
        pl_centers.append((key, frac, name, amt, center_y, bold))
        cum += frac

    add("\n  pickup pencircle scaled 1.0pt;\n\n")

    # BS 枠 & 中央分割
    add("  %% BS outline + center divider\n")
    add("  draw (0, h)--(2w, h);\n")
    add("  draw (0, 0)--(2w, 0);\n")
    add("  draw (0, 0)--(0, h);\n")
    add("  draw (2w, 0)--(2w, h);\n")
    add("  draw (w, 0)--(w, h);\n\n")

    add("  %% BS asset dividers\n")
    cum = 0.0
    for key, frac, _, _ in asset_cells[:-1]:
        cum += frac
        add(f"  draw (0, (1 - {cum:.5f})*h)--(w, (1 - {cum:.5f})*h);\n")
    add("  %% BS L+E dividers\n")
    cum = 0.0
    for key, frac, _, _ in le_cells[:-1]:
        cum += frac
        add(f"  draw (w, (1 - {cum:.5f})*h)--(2w, (1 - {cum:.5f})*h);\n")

    # PL 枠 & 中央分割 (赤字時は pl_total を底とする)
    add("\n  %% PL outline + center divider\n")
    add(f"  draw (3w, h)--(5w, h);\n")
    add(f"  draw (3w, (1-{pl_total:.5f})*h)--(5w, (1-{pl_total:.5f})*h);\n")
    add(f"  draw (3w, h)--(3w, (1-{pl_total:.5f})*h);\n")
    add(f"  draw (5w, h)--(5w, (1-{pl_total:.5f})*h);\n")
    add(f"  draw (4w, h)--(4w, (1-{pl_total:.5f})*h);\n")
    if is_loss:
        # 売上高 と 当期純損失 の境界 (貸方=右半分のみ)
        add(f"  draw (4w, (1-{c['s']:.5f})*h)--(5w, (1-{c['s']:.5f})*h);\n")
    add("  %% PL cost dividers\n")
    cum = 0.0
    for key, frac, _, _, _, _ in pl_centers[:-1]:
        cum += frac
        add(f"  draw (3w, (1 - {cum:.5f})*h)--(4w, (1 - {cum:.5f})*h);\n")

    add("\n  %% Section headers\n")
    add(f"  label.top(btex {_sizecmd(20)}\\bfseries BS etex, (w, h + 4mm));\n")
    add(f"  label.top(btex {_sizecmd(20)}\\bfseries PL etex, (4w, h + 4mm));\n\n")

    # 総資産の両矢印ブラケット
    add("  %% Total assets bracket\n")
    add("  path p;\n")
    add("  p := (-0.18w, 0)--(-0.18w, h);\n")
    add("  drawarrow p;\n")
    add("  drawarrow reverse p;\n")
    add(f"  label.lft(btex {_sizecmd(13)}\\shortstack{{総資産\\\\"
        f"{yen_label(T)}" "} etex, (-0.20w, 0.5h));\n\n")

    # 資産側ラベル
    add("  %% BS asset labels\n")
    for key, frac, name, amt, cy in asset_centers:
        bold = (key == BOLD_BS_ASSET)
        add(emit_label(name, amt, frac, "0.5w", cy, bold=bold))

    # L+E ラベル
    add("  %% BS L+E labels\n")
    for key, frac, name, amt, cy in le_centers:
        bold = (key == BOLD_BS_LE)
        add(emit_label(name, amt, frac, "1.5w", cy,
                       outside_x="2.05w", leader_inner_x="2w", bold=bold))

    # PL ラベル (売上高: 貸方=右、収まる限り最大フォント)
    add("  %% PL labels\n")
    rev_amt = yen_label(d["revenue"])
    rev_center_y = f"(1 - {0.5 * c['s']:.5f})*h"
    add(emit_label("売上高", rev_amt, c["s"], "4.5w", rev_center_y))

    # 当期純損失 ラベル (貸方=右、売上高の下)
    if is_loss:
        loss_amt = yen_label(-d["net_income"])
        loss_cy = f"(1 - {c['s'] + 0.5 * loss_frac:.5f})*h"
        loss_bold = (BOLD_PL == "e4")
        add(emit_label("当期純損失", loss_amt, loss_frac, "4.5w", loss_cy,
                       outside_x="5.05w", leader_inner_x="5w",
                       bold=loss_bold, outside_dir="rt"))

    for key, frac, name, amt, cy, bold in pl_centers:
        # 費用列の極小セルの外部ラベルは左 (BS-PL の中央余白) に出す
        add(emit_label(name, amt, frac, "3.5w", cy,
                       outside_x="2.95w", leader_inner_x="3.1w",
                       bold=bold, outside_dir="lft"))

    # 総資産回転率 (PL 下部)
    add(f"\n  label.bot(btex {_sizecmd(13)}総資産回転率 $=$"
        f" {c['s']*100:.1f}\\% etex, (4w, (1-{pl_total:.5f})*h - 5mm));\n")

    add("endfig;\n")
    return "".join(out)


# タイトル無し (図のみ) がデフォルト。社名・年度は図に載せず、ファイル名で判別する。
LATEX_HEAD = r"""\documentclass[11pt]{ltjsarticle}
\usepackage[paperwidth=560mm,paperheight=320mm,margin=12mm]{geometry}
\usepackage{luamplib}
\renewcommand{\kanjifamilydefault}{\gtdefault}
\renewcommand{\familydefault}{\sfdefault}
\pagestyle{empty}

\begin{document}

\noindent\makebox[\textwidth][c]{%
\begin{mplibcode}
"""

LATEX_TAIL = r"""\end{mplibcode}
}

\end{document}
"""


def render_tex(d):
    """タイトル無し (図のみ) の TeX を返す。年度はファイル名で判別する。"""
    c = compute(d)
    mp_code = build_metapost(d, c)
    return LATEX_HEAD + mp_code + LATEX_TAIL


def _compile_to_cropped_pdf(td, out_name, tex_source):
    """lualatex × 2 → qpdf 1ページ抽出 → pdfcrop。"""
    tdp = Path(td)
    (tdp / f"{out_name}.tex").write_text(tex_source, encoding="utf-8")
    for _ in range(2):
        res = subprocess.run(
            ["lualatex", "-interaction=nonstopmode", f"{out_name}.tex"],
            cwd=td, capture_output=True, text=True,
        )
    pdf_src = tdp / f"{out_name}.pdf"
    if not pdf_src.exists():
        print("Last log tail:\n", res.stdout[-3000:])
        raise SystemExit(f"PDF not produced for {out_name}")
    crop_src = tdp / f"{out_name}.p1.pdf"
    subprocess.run(
        ["qpdf", str(pdf_src), "--pages", str(pdf_src), "1", "--",
         str(crop_src)], check=True)
    cropped = tdp / f"{out_name}-crop.pdf"
    subprocess.run(
        ["pdfcrop", str(crop_src), str(cropped)],
        check=True, capture_output=True)
    return cropped


def build(key, d):
    tex = render_tex(d)
    out_name = f"{FILE_PREFIX}_proportional_fs_{key}"
    with tempfile.TemporaryDirectory() as td:
        cropped = _compile_to_cropped_pdf(td, out_name, tex)
        FIGS.mkdir(parents=True, exist_ok=True)
        shutil.copy(cropped, FIGS / f"{out_name}.pdf")
        shutil.copy(Path(td) / f"{out_name}.tex", FIGS / f"{out_name}.tex")
        print(f"Built: {FIGS / (out_name + '.pdf')}")


def build_png(key, d):
    tex = render_tex(d)
    out_name = f"proportional_bs_pl_{key}"
    out_dir = FIGS / "slides"
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        cropped = _compile_to_cropped_pdf(td, out_name, tex)
        png_prefix = Path(td) / f"{out_name}_tmp"
        subprocess.run(
            ["pdftoppm", "-r", "300", "-png", str(cropped), str(png_prefix)],
            check=True)
        png_src = next(Path(td).glob(f"{out_name}_tmp-*.png"))
        png_dst = out_dir / f"{out_name}.png"
        shutil.copy(png_src, png_dst)
        print(f"Built: {png_dst}")


if __name__ == "__main__":
    for key, d in DATA.items():
        build(key, d)
        build_png(key, d)
