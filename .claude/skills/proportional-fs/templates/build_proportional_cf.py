#!/usr/bin/env python3
"""連結キャッシュ・フロー計算書の比例縮尺図を生成する。

各年度について、営業 CF、投資 CF、財務 CF を符号により
資金源泉 (LEFT 列) / 資金使途 (RIGHT 列) に振り分けて積み上げ、
両列を「現金純増減」分のバランス・セルで完全一致させる。
複数年度を**同一スケール** (mm/億円) で描き、視覚的に比較できる。

現金 (キャッシュ) は借方項目なので、その増加であるキャッシュ・インフロー
(資金源泉) を LEFT 列に、流出であるキャッシュ・アウトフロー (資金使途) を
RIGHT 列に置く。

出力は次の 2 系統:

  figs/<FILE_PREFIX>_cf_proportional_<key>.pdf       (タイトル無し、配布用)
  figs/slides/proportional_cf_<key>.png               (タイトル無し、Keynote 用、300 dpi)

スキル本体: ~/.claude/skills/proportional-fs/SKILL.md
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
BOLD_CF_SOURCE = "financing"   # operating / investing / financing。源泉側で強調する CF
BOLD_CF_USE    = "operating"   # 使途側で強調する CF (= 大きな資金流出元を強調)

# CF データ (単位: 億円 = 百万円 / 100)。3 期分などを辞書化して並べる。
DATA = {
    "fy2006": {
        "label_year":   "第16期 (2006年3月期)",
        "operating_cf": -330,
        "investing_cf":  +11,
        "financing_cf": +430,
    },
    # "fy2007": {...},
    # "fy2008": {...},
}

# === 描画コンベンション (通常は編集不要) =================================

SHADE = {
    "operating": 0.78,
    "investing": 0.93,
    "financing": 0.84,
    "cash_inc":  0.97,
    "cash_dec":  0.97,
}

T_TWO_LINE = 0.09
T_ONE_LINE = 0.04

# フォントは大・小の 2 段階のみ。列幅 W=60mm と一致させること。
COL_W_MM = 60.0
PT2MM = 0.3528
FONT_LARGE_PT = 16
FONT_SMALL_PT = 11


def _sizecmd(pt):
    return f"\\fontsize{{{pt}}}{{{pt * 1.16:.1f}}}\\selectfont "


def _em_width(s):
    return sum(1.0 if ord(ch) >= 0x2E80 else 0.5 for ch in s)


def _fits_2line(name, amount, pt, wc_mm, hc_mm):
    max_em = max(_em_width(name), _em_width(amount))
    w = max_em * pt * PT2MM
    h = 2 * 1.22 * pt * PT2MM
    return w <= 0.86 * wc_mm and h <= 0.82 * hc_mm


CF_NAMES = {
    "operating": "営業 CF",
    "investing": "投資 CF",
    "financing": "財務 CF",
    # キャッシュは現金だけでなく現金同等物を含むため「資金」と呼ぶ (列見出しの資金源泉/使途とも整合)
    "cash_inc":  "資金増加",
    "cash_dec":  "資金減少",
}


# === ロジック (通常は編集不要) ===========================================

def yen_label(amount_oku, signed=True):
    sign = ""
    if signed:
        if amount_oku >= 0:
            sign = "+"
        else:
            sign = "$-$"
            amount_oku = -amount_oku
    return f"{sign}{amount_oku:,}億円"


def compute(d):
    op  = d["operating_cf"]
    inv = d["investing_cf"]
    fin = d["financing_cf"]
    net = op + inv + fin

    sources = []
    for key, val in [("operating", op), ("investing", inv), ("financing", fin)]:
        if val > 0:
            sources.append((key, val, CF_NAMES[key]))
    if net < 0:
        sources.append(("cash_dec", -net, CF_NAMES["cash_dec"]))

    uses = []
    for key, val in [("operating", op), ("investing", inv), ("financing", fin)]:
        if val < 0:
            uses.append((key, -val, CF_NAMES[key]))
    if net > 0:
        uses.append(("cash_inc", net, CF_NAMES["cash_inc"]))

    total = sum(v for _, v, _ in sources)
    total_chk = sum(v for _, v, _ in uses)
    assert total == total_chk, f"Source/use mismatch: {total} vs {total_chk}"

    return {
        "operating_cf": op, "investing_cf": inv, "financing_cf": fin,
        "net": net,
        "sources": sources,
        "uses": uses,
        "total": total,
    }


def emit_label(name, amount_signed_str, frac_in_col, x_center, y_center,
               outside_x=None, leader_inner_x=None, bold=False,
               outside_side="rt", h_mm=115.0):
    """大・小 2 段階のフォントでラベルを置く (大が収まらなければ小に落とす)。"""
    bo = "\\bfseries " if bold else ""
    hc = frac_in_col * h_mm
    wc = COL_W_MM
    if frac_in_col >= T_TWO_LINE:
        for pt in (FONT_LARGE_PT, FONT_SMALL_PT):
            if _fits_2line(name, amount_signed_str, pt, wc, hc):
                body = f"{_sizecmd(pt)}{bo}\\shortstack{{{name}\\\\{amount_signed_str}}}"
                return f"  label(btex {body} etex, ({x_center}, {y_center}));\n"
    if frac_in_col >= T_ONE_LINE:
        body = f"{_sizecmd(FONT_SMALL_PT)}{bo}{name} {amount_signed_str}"
        return f"  label(btex {body} etex, ({x_center}, {y_center}));\n"
    body = f"{_sizecmd(FONT_SMALL_PT)}{bo}{name} {amount_signed_str}"
    pos_macro = "label.rt" if outside_side == "rt" else "label.lft"
    return (
        f"  {pos_macro}(btex {body} etex, ({outside_x}, {y_center}));\n"
        f"  draw ({leader_inner_x}, {y_center})--({outside_x}, {y_center});\n"
    )


def build_metapost(d, c, scale_mm_per_oku):
    out = []
    add = out.append

    add("beginfig(1);\n")
    add("  numeric H, W, gap;\n")
    add(f"  H := {c['total']*scale_mm_per_oku:.3f}mm;\n")
    add("  W := 60mm;\n")
    add("  gap := 18mm;\n\n")

    def emit_column(side, x_left, x_right, items):
        cum = 0
        for key, val, name in items:
            top = cum
            bot = cum + val
            yt = f"{(c['total']-top)*scale_mm_per_oku:.3f}mm"
            yb = f"{(c['total']-bot)*scale_mm_per_oku:.3f}mm"
            shade = SHADE[key]
            add(f"  %% {side} {name} {val}億\n")
            add(f"  fill ({x_left}, {yb})--({x_right}, {yb})"
                f"--({x_right}, {yt})--({x_left}, {yt})--cycle"
                f" withcolor {shade}white;\n")
            cum = bot

    # キャッシュは借方項目なので、増加 (インフロー=資金源泉) を左、使途を右に置く。
    add("  %% --- SOURCE side (LEFT) ---\n")
    emit_column("source", "0", "W", c["sources"])
    add("\n  %% --- USE side (RIGHT) ---\n")
    emit_column("use", "W+gap", "2W+gap", c["uses"])

    add("\n  pickup pencircle scaled 1.0pt;\n")
    add("  %% Outlines\n")
    add(f"  draw (0,0)--(W,0)--(W,H)--(0,H)--cycle;\n")
    add(f"  draw (W+gap,0)--(2W+gap,0)--(2W+gap,H)--(W+gap,H)--cycle;\n")

    add("  %% LEFT dividers (sources)\n")
    cum = 0
    for i, (_, val, _) in enumerate(c["sources"]):
        cum += val
        if i < len(c["sources"]) - 1:
            y = f"{(c['total']-cum)*scale_mm_per_oku:.3f}mm"
            add(f"  draw (0, {y})--(W, {y});\n")

    add("  %% RIGHT dividers (uses)\n")
    cum = 0
    for i, (_, val, _) in enumerate(c["uses"]):
        cum += val
        if i < len(c["uses"]) - 1:
            y = f"{(c['total']-cum)*scale_mm_per_oku:.3f}mm"
            add(f"  draw (W+gap, {y})--(2W+gap, {y});\n")

    h_mm = c["total"] * scale_mm_per_oku

    add("\n  %% Column headers\n")
    add(f"  label.top(btex {_sizecmd(20)}\\bfseries 資金源泉 etex, (0.5W, H + 4mm));\n")
    add(f"  label.top(btex {_sizecmd(20)}\\bfseries 資金使途"
        " etex, (1.5W+gap, H + 4mm));\n")

    # LEFT (source) labels
    add("\n  %% LEFT labels (sources)\n")
    cum = 0
    for key, val, name in c["sources"]:
        frac = val / c["total"]
        cy = f"{(c['total']-cum - 0.5*val)*scale_mm_per_oku:.3f}mm"
        if key == "cash_dec":
            amt_str = yen_label(val, signed=False)
            bold = False
        else:
            amt_str = yen_label(val, signed=True)
            bold = (key == BOLD_CF_SOURCE)
        add(emit_label(name, amt_str, frac,
                       "0.5W", cy,
                       outside_x="-3mm",
                       leader_inner_x="0",
                       outside_side="lft",
                       bold=bold, h_mm=h_mm))
        cum += val

    # RIGHT (use) labels
    add("\n  %% RIGHT labels (uses)\n")
    cum = 0
    for key, val, name in c["uses"]:
        frac = val / c["total"]
        cy = f"{(c['total']-cum - 0.5*val)*scale_mm_per_oku:.3f}mm"
        if key == "cash_inc":
            amt_str = yen_label(val, signed=False)
            bold = False
        else:
            amt_str = yen_label(-val, signed=True)   # 元の符号 (負) を表示
            bold = (key == BOLD_CF_USE)
        add(emit_label(name, amt_str, frac,
                       "1.5W+gap", cy,
                       outside_x="2W+gap+0.1*gap",
                       leader_inner_x="2W+gap",
                       outside_side="rt",
                       bold=bold, h_mm=h_mm))
        cum += val

    # 現金純増減キャプション
    net = c["net"]
    if net >= 0:
        net_label = f"現金及び現金同等物の純増加 $=$ {abs(net):,}億円"
    else:
        net_label = f"現金及び現金同等物の純減少 $=$ {abs(net):,}億円"
    add(f"\n  label.bot(btex {_sizecmd(13)}{net_label} etex,"
        f" (0.5*(2W+gap), -7mm));\n")

    add("endfig;\n")
    return "".join(out)


# タイトル無し (図のみ) がデフォルト。社名・年度は図に載せず、ファイル名で判別する。
LATEX_HEAD = r"""\documentclass[11pt]{ltjsarticle}
\usepackage[paperwidth=460mm,paperheight=320mm,margin=12mm]{geometry}
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


def compute_global_scale():
    """全年度を通じた単一スケール (mm/億円) を算定。最大年度を約 115mm に。"""
    totals = [compute(d)["total"] for d in DATA.values()]
    max_total = max(totals)
    return 115.0 / max_total, max_total


def _compile_to_cropped_pdf(td, out_name, tex_source):
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


def build(key, d, scale):
    c = compute(d)
    mp = build_metapost(d, c, scale)
    tex = LATEX_HEAD + mp + LATEX_TAIL
    out_name = f"{FILE_PREFIX}_cf_proportional_{key}"
    with tempfile.TemporaryDirectory() as td:
        cropped = _compile_to_cropped_pdf(td, out_name, tex)
        FIGS.mkdir(parents=True, exist_ok=True)
        shutil.copy(cropped, FIGS / f"{out_name}.pdf")
        shutil.copy(Path(td) / f"{out_name}.tex", FIGS / f"{out_name}.tex")
        print(f"Built: {FIGS / (out_name + '.pdf')}")


def build_png(key, d, scale):
    c = compute(d)
    mp = build_metapost(d, c, scale)
    tex = LATEX_HEAD + mp + LATEX_TAIL
    out_name = f"proportional_cf_{key}"
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
    scale, max_total = compute_global_scale()
    print(f"Global scale: {scale:.4f} mm/億円 (max total = {max_total:,}億)")
    for key, d in DATA.items():
        build(key, d, scale)
        build_png(key, d, scale)
