"""Auditable reconstruction of Enomoto et al. (2024).

This deliberately does not call either lane an exact replication: the local FQ
extract does not identify notes/accrued payables for PPE or long-term allowances,
and the paper's NLI mutual-holdings file is unavailable.  The script preserves
those limitations in every machine-readable output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


FQ_DEFAULT = Path(r"C:\Data\fq\processed\AccountingExp.csv")
FINANCE = {47, 49, 51, 52}
RAW = {
    "FIRM": "firm_name", "NKCODE": "firm_id", "FiscalEnd": "fiscal_end",
    "Listing": "listed", "MACC": "months", "Industry": "industry_name",
    "CodeIndustry": "industry", "A01_SCFLG": "scope_code",
    "A01_SECFLG": "basis_code", "B01110": "assets",
    "B01021": "current_assets", "B01022": "cash",
    "B01033": "trading_securities", "B01051": "short_loans_receivable",
    "C01021": "current_liabilities", "C01026": "short_debt",
    "C01058": "long_debt", "C01106": "book_equity", "B01063": "ppe",
    "D01021": "sales", "F01065": "cfo_reported", "H01005": "depreciation",
    "D01114": "ni_total", "D01110": "ni_parent", "D01105": "ni_nci",
    "D01067": "extra_gain", "D01081": "extra_loss", "MVFE": "market_equity",
    "SourceMissingAssets": "source_missing_assets",
    "SourceMissingPPEAny": "source_missing_ppe_any",
}
AXES = {1: "JGAAP", 2: "USGAAP", 3: "IFRS"}


def safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a.div(b.where(b.gt(0)))


def _winsor(s: pd.Series) -> pd.Series:
    q = s.quantile([.01, .99])
    return s.clip(q.iloc[0], q.iloc[1]) if len(q) == 2 else s


def negative_prior_five_sd(residual: pd.Series, firm: pd.Series,
                           continuity_break: pd.Series) -> pd.Series:
    """Higher values denote better AQ; current-period residual is excluded."""
    shifted = residual.groupby(firm).shift()
    segment = continuity_break.groupby(firm).cumsum()
    return -shifted.groupby([firm, segment]).transform(
        lambda s: s.rolling(5, min_periods=5).std())


def load_panel(path: Path, end_year: int) -> tuple[pd.DataFrame, list[dict]]:
    x = pd.read_csv(path, usecols=list(RAW), low_memory=False).rename(columns=RAW)
    x["fiscal_end"] = pd.to_datetime(x["fiscal_end"], errors="coerce")
    x["year"] = x.fiscal_end.dt.year
    flow = [{"stage": "raw selected columns", "n": len(x)}]
    tests = [
        ("listed", x.listed.eq(1)),
        ("consolidated_only", x.scope_code.eq(2)),
        ("twelve_month", x.months.eq(12)),
        ("nonfinancial_known_industry", x.industry.notna() & ~x.industry.isin(FINANCE)),
        ("positive_raw_assets", x.assets.gt(0) & ~x.source_missing_assets.fillna(True)),
        ("history_and_analysis_horizon", x.year.between(1980, end_year)),
    ]
    for name, keep in tests:
        x = x.loc[keep.reindex(x.index).fillna(False)].copy()
        flow.append({"stage": name, "n": len(x)})
    x = x.sort_values(["firm_id", "fiscal_end"]).drop_duplicates(["firm_id", "fiscal_end"], keep="last")
    flow.append({"stage": "unique_firm_period", "n": len(x)})
    x["statementScope"] = "consolidated"
    x["accountingBasis"] = x.basis_code.map(AXES).fillna("unknown")
    x["periodMeasure"] = "annual_12_month"
    x["disclosureChannel"] = "FQ_vendor"
    return x.reset_index(drop=True), flow


def add_measurements(x: pd.DataFrame, *, missing_as_zero_proxy: bool = False) -> pd.DataFrame:
    x = x.copy().sort_values(["firm_id", "fiscal_end"])
    if "year" not in x:
        x["year"] = x.fiscal_end.dt.year
    g = x.groupby("firm_id", sort=False)
    prior_date = g.fiscal_end.shift()
    next_date = g.fiscal_end.shift(-1)
    prior_basis = g.accountingBasis.shift()
    next_basis = g.accountingBasis.shift(-1)
    x["lag_ok"] = x.fiscal_end.sub(prior_date).dt.days.between(330, 400) & x.accountingBasis.eq(prior_basis)
    x["lead_ok"] = next_date.sub(x.fiscal_end).dt.days.between(330, 400) & x.accountingBasis.eq(next_basis)
    x["continuity_break"] = ~x.lag_ok.fillna(False)
    for c in ["assets", "current_assets", "cash", "trading_securities", "short_loans_receivable",
              "current_liabilities", "short_debt", "ppe", "sales"]:
        x[f"lag_{c}"] = g[c].shift().where(x.lag_ok)
    avg_assets = (x.assets + x.lag_assets) / 2
    # Missing-as-zero is never the main lane.  It exists only as an explicitly
    # named sensitivity because item-level SourceMissing flags are unavailable.
    item = (lambda s: s.fillna(0)) if missing_as_zero_proxy else (lambda s: s)
    x["missingItemPolicy"] = ("missing_as_zero_proxy_sensitivity" if missing_as_zero_proxy
                              else "raw_complete_case")
    # FQ does not expose the paper's PPE-note and PPE-accrued-payable components.
    nwc = (x.current_assets - x.cash - item(x.trading_securities)
           - item(x.short_loans_receivable) - x.current_liabilities + item(x.short_debt))
    lag_nwc = nwc.groupby(x.firm_id, sort=False).shift().where(x.lag_ok)
    x["tca"] = safe_div((nwc - lag_nwc).where(x.lag_ok), avg_assets)
    x["delta_sales"] = safe_div(x.sales - x.lag_sales, avg_assets)
    x["ppe_scaled"] = safe_div(x.ppe, avg_assets)
    ni = x.ni_total.combine_first(x.ni_parent + item(x.ni_nci))
    ebeI = ni - item(x.extra_gain) + item(x.extra_loss)
    # Reconstruction: missing long-term allowance and two PPE-payable deltas are explicit omissions.
    total_accrual_amount = (nwc - lag_nwc).where(x.lag_ok) - x.depreciation
    x["cfo_reconstructed"] = safe_div(ebeI - total_accrual_amount, avg_assets)
    x["cfo_statement"] = safe_div(x.cfo_reported, avg_assets)
    x["invest"] = safe_div(x.ppe - x.lag_ppe + x.depreciation, x.lag_assets)
    x["cash_ratio"] = safe_div(x.cash, x.assets)
    debt = item(x.short_debt) + x.long_debt
    x["neg_leverage"] = -safe_div(debt, x.assets)
    for c in ["cash_ratio", "neg_leverage"]:
        rank = x.groupby("year")[c].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False, duplicates="drop"))
        x[f"rank_{c}"] = rank / 9
    x["over_i"] = x[["rank_cash_ratio", "rank_neg_leverage"]].mean(axis=1)
    x["log_assets"] = np.log(x.assets.where(x.assets.gt(0)))
    x["mtb"] = safe_div(x.market_equity + (x.assets - x.book_equity), x.assets)
    x["tangibility"] = safe_div(x.ppe, x.assets)
    x["cfo_sales_statement"] = safe_div(x.cfo_reported, x.sales)
    # Reconstructed CFO is scaled by average assets above; convert it back to
    # an amount before forming the paper's CFO-to-sales control.
    x["cfo_sales_reconstructed"] = safe_div(x.cfo_reconstructed * avg_assets, x.sales)
    x["loss"] = ni.lt(0).where(ni.notna()).astype(float)
    return x


def estimate_aq(x: pd.DataFrame, cfo_col: str, lane: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    z = x.copy()
    g = z.groupby("firm_id", sort=False)
    z["cfo_lag"] = g[cfo_col].shift().where(z.lag_ok)
    z["cfo_lead"] = g[cfo_col].shift(-1).where(z.lead_ok)
    cols = ["tca", "cfo_lag", cfo_col, "cfo_lead", "delta_sales", "ppe_scaled"]
    for c in cols:
        z[f"w_{c}"] = _winsor(z[c])
    residual = pd.Series(np.nan, index=z.index)
    diag = []
    for (year, industry), q in z.groupby(["year", "industry"]):
        q = q.dropna(subset=[f"w_{c}" for c in cols])
        row = {"lane": lane, "year": year, "industry": industry, "n_complete": len(q), "estimated": False}
        if len(q) >= 20:
            X = sm.add_constant(q[[f"w_{c}" for c in cols[1:]]], has_constant="add")
            fit = sm.OLS(q[f"w_{cols[0]}"], X).fit()
            residual.loc[q.index] = fit.resid
            row.update(estimated=True, r2=fit.rsquared)
        diag.append(row)
    z[f"resid_{lane}"] = residual
    # Exactly the five preceding residuals, never the current residual.
    z[f"aq_{lane}"] = negative_prior_five_sd(
        z[f"resid_{lane}"], z.firm_id, z.continuity_break)
    return z, pd.DataFrame(diag)


def fit_core(x: pd.DataFrame, aq: str, lane: str, start: int, end: int) -> tuple[pd.DataFrame, dict]:
    cfo_control = ("cfo_sales_reconstructed" if lane.startswith("history_reconstructed")
                   else "cfo_sales_statement")
    controls = ["log_assets", "mtb", "tangibility", cfo_control, "loss"]
    q = x.loc[x.year.between(start, end)].copy()
    q["aq_over_i"] = q[aq] * q.over_i
    vars_ = ["invest", aq, "aq_over_i", "over_i", *controls, "industry", "year"]
    q = q.dropna(subset=vars_)
    for c in ["invest", aq, "aq_over_i", "over_i", *controls]:
        q[c] = _winsor(q[c])
    if len(q) < 50:
        return pd.DataFrame(), {"lane": lane, "period": f"{start}-{end}", "n": len(q), "status": "insufficient"}
    X = pd.concat([q[[aq, "aq_over_i", "over_i", *controls]],
                   pd.get_dummies(q.industry, prefix="ind", drop_first=True, dtype=float),
                   pd.get_dummies(q.year, prefix="yr", drop_first=True, dtype=float)], axis=1)
    fit = sm.OLS(q.invest, sm.add_constant(X, has_constant="add")).fit(cov_type="cluster", cov_kwds={"groups": q.firm_id})
    terms = [aq, "aq_over_i", "over_i", *controls]
    coef = pd.DataFrame({"lane": lane, "period": f"{start}-{end}", "term": terms,
                         "coefficient": fit.params[terms], "std_error": fit.bse[terms],
                         "p_value": fit.pvalues[terms]}).reset_index(drop=True)
    meta = {"lane": lane, "period": f"{start}-{end}", "n": len(q), "firms": int(q.firm_id.nunique()),
            "min_year": int(q.year.min()), "max_year": int(q.year.max()), "r2": fit.rsquared,
            "status": "reconstructed_core_missing_ownership_and_full_controls"}
    return coef, meta


def fit_regime_differences(x: pd.DataFrame, end_year: int) -> pd.DataFrame:
    """Cluster-robust formal slope comparisons for pre, paper, and extension regimes."""
    aq = "aq_history_reconstructed"
    controls = ["log_assets", "mtb", "tangibility", "cfo_sales_reconstructed", "loss"]
    q = x.loc[x.year.between(1986, end_year)].copy()
    base = ["invest", aq, "over_i", *controls]
    q = q.dropna(subset=[*base, "industry", "year"])
    for c in base:
        q[c] = _winsor(q[c])
    q["aq_over_i"] = q[aq] * q.over_i
    q["paper"] = q.year.between(2002, 2013).astype(float)
    q["extension"] = q.year.ge(2014).astype(float)
    q["aq_paper"] = q[aq] * q.paper
    q["aq_extension"] = q[aq] * q.extension
    q["aq_over_i_paper"] = q.aq_over_i * q.paper
    q["aq_over_i_extension"] = q.aq_over_i * q.extension
    regressors = [aq, "aq_over_i", "over_i", "aq_paper", "aq_extension",
                  "aq_over_i_paper", "aq_over_i_extension", *controls]
    X = pd.concat([q[regressors],
                   pd.get_dummies(q.industry, prefix="ind", drop_first=True, dtype=float),
                   pd.get_dummies(q.year, prefix="yr", drop_first=True, dtype=float)], axis=1)
    fit = sm.OLS(q.invest, sm.add_constant(X, has_constant="add")).fit(
        cov_type="cluster", cov_kwds={"groups": q.firm_id})
    comparisons = [
        ("paper_minus_pre", "aq", {"aq_paper": 1}),
        ("extension_minus_pre", "aq", {"aq_extension": 1}),
        ("extension_minus_paper", "aq", {"aq_extension": 1, "aq_paper": -1}),
        ("paper_minus_pre", "aq_over_i", {"aq_over_i_paper": 1}),
        ("extension_minus_pre", "aq_over_i", {"aq_over_i_extension": 1}),
        ("extension_minus_paper", "aq_over_i", {"aq_over_i_extension": 1, "aq_over_i_paper": -1}),
    ]
    rows = []
    names = list(fit.params.index)
    for comparison, slope, weights in comparisons:
        contrast = np.zeros(len(names))
        for term, weight in weights.items():
            contrast[names.index(term)] = weight
        test = fit.t_test(contrast)
        rows.append({"comparison": comparison, "slope": slope,
                     "coefficient_difference": float(np.asarray(test.effect).ravel()[0]),
                     "std_error": float(np.asarray(test.sd).ravel()[0]),
                     "p_value": float(np.asarray(test.pvalue).ravel()[0]),
                     "n": len(q), "firms": q.firm_id.nunique(),
                     "min_year": q.year.min(), "max_year": q.year.max()})
    return pd.DataFrame(rows)


def fit_break_stability(x: pd.DataFrame, break_year: int) -> pd.DataFrame:
    """Test changes in both AQ slopes around alternative Act break years."""
    aq = "aq_history_reconstructed"
    controls = ["log_assets", "mtb", "tangibility", "cfo_sales_reconstructed", "loss"]
    q = x.loc[x.year.between(1986, 2013)].copy()
    q["aq_over_i"] = q[aq] * q.over_i
    q["post"] = q.year.gt(break_year).astype(float)
    q["aq_post"] = q[aq] * q.post
    q["aq_over_i_post"] = q.aq_over_i * q.post
    needed = ["invest", aq, "aq_over_i", "over_i", "post", "aq_post",
              "aq_over_i_post", *controls, "industry", "year"]
    q = q.dropna(subset=needed)
    continuous = ["invest", aq, "aq_over_i", "over_i", "aq_post",
                  "aq_over_i_post", *controls]
    for c in continuous:
        q[c] = _winsor(q[c])
    regressors = [aq, "aq_over_i", "over_i", "post", "aq_post",
                  "aq_over_i_post", *controls]
    X = pd.concat([q[regressors],
                   pd.get_dummies(q.industry, prefix="ind", drop_first=True, dtype=float),
                   pd.get_dummies(q.year, prefix="yr", drop_first=True, dtype=float)], axis=1)
    fit = sm.OLS(q.invest, sm.add_constant(X, has_constant="add")).fit(
        cov_type="cluster", cov_kwds={"groups": q.firm_id})
    terms = ["aq_post", "aq_over_i_post"]
    return pd.DataFrame({"break_after_year": break_year, "n": len(q), "firms": q.firm_id.nunique(),
                         "term": terms, "coefficient_change": fit.params[terms],
                         "std_error": fit.bse[terms], "p_value": fit.pvalues[terms]})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fq", type=Path, default=FQ_DEFAULT)
    ap.add_argument("--output", type=Path, default=Path("outputs/enomoto_2024"))
    ap.add_argument("--end-year", type=int, default=2024)
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    for obsolete_name in (
        "break_stability.csv",
        "regime_slope_differences.csv",
        "same_period_cfo_comparison.csv",
        "same_period_cfo_samples.csv",
    ):
        (args.output / obsolete_name).unlink(missing_ok=True)
    panel, flow = load_panel(args.fq, args.end_year)
    x = add_measurements(panel, missing_as_zero_proxy=False)
    diagnostics = []
    for cfo, lane in [("cfo_reconstructed", "history_reconstructed"), ("cfo_statement", "cf_statement")]:
        x, d = estimate_aq(x, cfo, lane); diagnostics.append(d)
    results, samples = [], []
    for lane in ["history_reconstructed", "cf_statement"]:
        aq = f"aq_{lane}"
        for start, end in [(1986, 2001), (2002, 2013), (2014, args.end_year)]:
            r, m = fit_core(x, aq, lane, start, end); results.append(r); samples.append(m)
    # Sensitivity only: emulate the legacy convention that unavailable raw
    # components represent zero.  Results never feed the main/core outputs.
    proxy = add_measurements(panel, missing_as_zero_proxy=True)
    proxy_diagnostics = []
    for cfo, lane in [("cfo_reconstructed", "history_reconstructed"),
                      ("cfo_statement", "cf_statement")]:
        proxy, d = estimate_aq(proxy, cfo, lane); proxy_diagnostics.append(d)
    proxy_results, proxy_samples = [], []
    for lane in ["history_reconstructed", "cf_statement"]:
        for start, end in [(1986, 2001), (2002, 2013), (2014, args.end_year)]:
            r, m = fit_core(proxy, f"aq_{lane}", lane, start, end)
            if not r.empty:
                r.insert(0, "missing_item_policy", "missing_as_zero_proxy_sensitivity")
            m["missing_item_policy"] = "missing_as_zero_proxy_sensitivity"
            proxy_results.append(r); proxy_samples.append(m)
    pd.DataFrame(flow).to_csv(args.output / "sample_flow.csv", index=False, encoding="utf-8-sig")
    pd.concat(diagnostics).to_csv(args.output / "aq_first_stage.csv", index=False, encoding="utf-8-sig")
    pd.concat(proxy_diagnostics).to_csv(args.output / "aq_first_stage_missing_as_zero_proxy.csv", index=False, encoding="utf-8-sig")
    pd.concat(results, ignore_index=True).to_csv(args.output / "core_coefficients.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(samples).to_csv(args.output / "model_samples.csv", index=False, encoding="utf-8-sig")
    pd.concat(proxy_results, ignore_index=True).to_csv(
        args.output / "missing_as_zero_proxy_coefficients.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(proxy_samples).to_csv(
        args.output / "missing_as_zero_proxy_samples.csv", index=False, encoding="utf-8-sig")
    common = proxy.loc[proxy.aq_history_reconstructed.notna() & proxy.aq_cf_statement.notna()
                       & proxy.cfo_sales_reconstructed.notna() & proxy.cfo_sales_statement.notna()].copy()
    common_results, common_samples = [], []
    for aq, lane in [("aq_history_reconstructed", "history_reconstructed_common_sample"),
                     ("aq_cf_statement", "cf_statement_common_sample")]:
        r, m = fit_core(common, aq, lane, 2006, 2013)
        common_results.append(r); common_samples.append(m)
    pd.concat(common_results, ignore_index=True).to_csv(
        args.output / "missing_as_zero_proxy_same_period_cfo_comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(common_samples).to_csv(
        args.output / "missing_as_zero_proxy_same_period_cfo_samples.csv", index=False, encoding="utf-8-sig")
    regime_differences = fit_regime_differences(proxy, args.end_year)
    regime_differences.to_csv(
        args.output / "missing_as_zero_proxy_regime_slope_differences.csv", index=False, encoding="utf-8-sig")
    stability = pd.concat([fit_break_stability(proxy, year) for year in range(1998, 2007)], ignore_index=True)
    stability.to_csv(
        args.output / "missing_as_zero_proxy_break_stability.csv", index=False, encoding="utf-8-sig")
    status = pd.DataFrame([
        {"lane": "exact", "status": "unavailable", "reason": "NLI mutual holdings, ownership controls, and exact accrual components unavailable"},
        {"lane": "raw_complete_case", "status": "history_unavailable_reported_cf_sparse", "reason": "history-reconstructed has no five-year AQ model sample; reported-CF retains only 69 observations in 2006-2009"},
        {"lane": "missing_as_zero_proxy", "status": "executed_sensitivity_only", "reason": "zero substitution is not interpreted as accounting zero"},
        {"lane": "period_extension", "status": "executed_proxy_sensitivity", "reason": f"out-of-paper 2014-{args.end_year} diagnostic"},
        {"lane": "cross_shareholding_moderation", "status": "unavailable", "reason": "local holdings file is not construct-equivalent to NLI mutual holdings"},
    ])
    status.to_csv(args.output / "replication_status.csv", index=False, encoding="utf-8-sig")
    reconstructed_samples = pd.DataFrame(samples).query("lane == 'history_reconstructed'")
    reconstructed_pre = int(reconstructed_samples.query("period == '1986-2001'").n.iloc[0])
    reconstructed_paper = int(reconstructed_samples.query("period == '2002-2013'").n.iloc[0])
    proxy_history = pd.DataFrame(proxy_samples).query("lane == 'history_reconstructed'")
    proxy_pre = int(proxy_history.query("period == '1986-2001'").n.iloc[0])
    proxy_paper = int(proxy_history.query("period == '2002-2013'").n.iloc[0])
    benchmark = pd.DataFrame([
        {"period": "1986-2001", "published_n": 8245, "raw_complete_case_n": reconstructed_pre, "missing_as_zero_proxy_n": proxy_pre},
        {"period": "2002-2013", "published_n": 21139, "raw_complete_case_n": reconstructed_paper, "missing_as_zero_proxy_n": proxy_paper},
        {"period": "1986-2013", "published_n": 29384, "raw_complete_case_n": reconstructed_pre + reconstructed_paper, "missing_as_zero_proxy_n": proxy_pre + proxy_paper},
    ])
    benchmark["proxy_minus_published"] = benchmark.missing_as_zero_proxy_n - benchmark.published_n
    benchmark.to_csv(args.output / "published_sample_benchmark.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([
        {"variable": "aq_history_reconstructed", "definition": "negative SD of exactly five prior first-stage residuals", "direction": "higher means higher accounting quality"},
        {"variable": "aq_cf_statement", "definition": "negative SD of exactly five prior first-stage residuals using reported CFO", "direction": "higher means higher accounting quality"},
    ]).to_csv(args.output / "variable_semantics.csv", index=False, encoding="utf-8-sig")
    axes = x.groupby(["statementScope", "accountingBasis", "periodMeasure", "disclosureChannel"], dropna=False).size().rename("n").reset_index()
    axes.to_csv(args.output / "accounting_axes.csv", index=False, encoding="utf-8-sig")
    missing = x.groupby("year").agg(n=("firm_id", "size"), basis_switch_breaks=("continuity_break", "sum"),
              cfo_reported=("cfo_reported", "count"), ppe=("ppe", "count"), depreciation=("depreciation", "count"))
    missing.to_csv(args.output / "missingness_continuity.csv", encoding="utf-8-sig")
    manifest = {
      "paper": {"citation": "Enomoto, Rhee, Jung, and Shuto (2024), JWE 72, 101280", "doi": "10.1016/j.japwor.2024.101280",
                "specification_source": "2020 SSRN working paper; final metadata verified; accepted manuscript unavailable locally"},
      "input": {"path": str(args.fq), "size": args.fq.stat().st_size, "mtime_ns": args.fq.stat().st_mtime_ns,
                "sha256_header": hashlib.sha256(",".join(pd.read_csv(args.fq,nrows=0).columns).encode()).hexdigest()},
      "axes_policy": "consolidated only (A01_SCFLG=2); basis retained from A01_SECFLG; annual 12-month; FQ vendor",
      "continuity_policy": "lag/lead require 330-400 days and unchanged accounting basis; methodology knowledge ID gate-time-series-transforms-on-continuity",
      "lanes": {"exact": "unavailable",
                "history_reconstructed": "main raw-complete-case lane; non-exact: omits PPE-note/accrued-payable deltas and long-term allowance",
                "cf_statement": "main raw-complete-case lane; post-2000 observed CFO, but same approximate TCA",
                "missing_as_zero_proxy": "sensitivity only; never used as main result",
                "period_extension": f"2014-{args.end_year}; diagnostic, not replication"},
      "unavailable": {"foreign_and_financial_ownership": "not present", "NLI_cross_shareholdings": "not present; FirmHoldings is not construct-equivalent",
                      "main_bank": "not constructed", "exact_table_3": True},
      "forbidden_sources_not_used": ["Analyst.csv", "Nikkei consensus", "analyst forecasts", "analyst coverage"],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = pd.DataFrame(samples).to_markdown(index=False)
    proxy_rows = pd.DataFrame(proxy_samples).to_markdown(index=False)
    report = f"""# Enomoto et al. (2024) 再現報告\n\n## 結論\n\n本成果は exact replication ではなく、利用可能な FQ raw 項目による再構成 core である。原論文の NLI 相互保有、外国人・金融機関持株、PPE 取得債務2項目、長期引当金が欠けるため、Table 3 の一致を主張しない。連結財務諸表のみを用い、単独への fallback は行っていない。\n\n## 版の扱い\n\n仕様は入手できた2020年SSRN working paperから復元し、2024年最終版の書誌情報とDOIを確認した。ただし最終accepted manuscript本文をローカルで取得できていないため、working paperから最終版への表・変数・標本変更は未検証である。\n\n## 主レーン（raw complete-case）\n\n{rows}\n\n対象raw項目のitem-level SourceMissingを検証できないため、主レーンは欠損を0にせずcomplete-caseとした。この条件では5期AQまで到達する推定標本が得られず、主レーン係数は推定不能である。\n\n## missing-as-zero proxy感応度\n\n{proxy_rows}\n\n以下の係数・安定性結果はすべてこのproxy感応度であり、会計上のゼロを確認した結果ではない。原論文の標本はpre 8,245件、2002--2013年21,139件、合計29,384件である。本再構成との差は `published_sample_benchmark.csv` に示す。これは同一母集団から順に落ちたattritionとは限らず、利用変数、業種分類、FQ収録範囲、working-paperと最終版の差を含む benchmark difference である。AQに5期の事前残差が必要なため、history laneの最初の推定年は1987年、reported-CF laneはFQのCFO開始後に履歴を蓄積して2006年となる。\n\n## AQの符号\n\nAQはfirst-stage残差の直前5年の標準偏差に負号を付けている。したがって値が大きい（0に近い）ほど会計品質が高い。実装は当期残差を含めず、連続した5期が揃う場合だけ値を与える。\n\n## 識別と安定性\n\n2002年開始は銀行株式保有制限法が2002年1月に施行されたという原論文のpre/post区分に従う。1986--2001、2002--2013、2014--{args.end_year} を事前固定した。後者は期間延長であり原論文再現ではない。proxyの3区分pooled slope differenceは `missing_as_zero_proxy_regime_slope_differences.csv`、1998--2006年境界感応度は `missing_as_zero_proxy_break_stability.csv` に保存した。いずれも政策効果の因果推定ではない。proxyのreported-CFとhistory-reconstructedの同一2006--2013年比較も明示名付きファイルに保存した。主係数は `core_coefficients.csv`、proxy係数は `missing_as_zero_proxy_coefficients.csv` に分離した。\n\n## 会計データの監査\n\n`statementScope`、`accountingBasis`、`periodMeasure`、`disclosureChannel` を別軸で保持した。raw assets欠損フラグを除外に使い、既存派生列の0を会計上の0とは解釈していない。主レーンでは trading securities、short-term loans receivable、short-term debt、NCI income、extraordinary gain/loss のraw欠損を0に置換せず、算式結果を欠損のままにする。ゼロ補完結果は明示的なproxy感応度として隔離し、主結果には使わない。基準変更は continuity break とした。B01063（純有形固定資産）については `SourceMissingPPEAny` が同じraw項目専用とは確認できないため、当該フラグによる除外はせず年別欠損を開示した。\n\n## moderation の監査\n\nローカル FirmHoldings は issuer の保有明細（DNKCODE、SHS、AV/BV）だが、NLI の調査母集団、相互保有識別、holder/issuer の完全な双方向対応を確認できない。このため cross-shareholding proxy は作成せず unavailable とした。\n"""
    report = report.replace(
        "この条件では5期AQまで到達する推定標本が得られず、主レーン係数は推定不能である。",
        "history-reconstructed lane は全期間で推定標本が0件となった。"
        "reported-CF lane は2006--2009年に69件（27社）のみ残り推定できたが、極端に疎である。"
        "その他の期間は0件である。",
    )
    (args.output / "report_ja.md").write_text(report, encoding="utf-8")
    print(pd.DataFrame(samples).to_string(index=False))
    combined_results = pd.concat(results, ignore_index=True)
    if not combined_results.empty:
        print(combined_results.query("term in ['aq_history_reconstructed','aq_cf_statement','aq_over_i']").to_string(index=False))

if __name__ == "__main__":
    main()
