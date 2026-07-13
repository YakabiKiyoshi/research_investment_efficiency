"""Expected-investment estimators and residual-based efficiency measures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from .panel import numeric, rank_zero_one, require_columns


@dataclass(frozen=True)
class ExpectedInvestmentResult:
    """Firm-year measures plus auditable first-stage outputs."""

    panel: pd.DataFrame
    coefficients: pd.DataFrame
    diagnostics: pd.DataFrame
    specification: str


def _design_matrix(
    sample: pd.DataFrame,
    *,
    predictors: Sequence[str],
    fixed_effects: Sequence[str],
) -> pd.DataFrame:
    design = pd.DataFrame({"Intercept": 1.0}, index=sample.index)
    for predictor in predictors:
        design[predictor] = numeric(sample[predictor])
    for fixed_effect in fixed_effects:
        dummies = pd.get_dummies(
            sample[fixed_effect].astype("string"),
            prefix=fixed_effect,
            drop_first=True,
            dtype=float,
        )
        design = pd.concat([design, dummies], axis=1)
    return design.astype(float)


def _remove_fixed_effect_singletons(
    sample: pd.DataFrame,
    fixed_effects: Sequence[str],
) -> tuple[pd.DataFrame, pd.Index]:
    """Iteratively remove levels represented by only one estimation row."""

    if not fixed_effects or sample.empty:
        return sample, sample.index[:0]
    active = pd.Series(True, index=sample.index)
    while active.any():
        subset = sample.loc[active]
        singleton = pd.Series(False, index=subset.index)
        for fixed_effect in fixed_effects:
            counts = subset.groupby(fixed_effect, sort=False)[fixed_effect].transform(
                "size"
            )
            singleton |= counts.eq(1)
        if not singleton.any():
            break
        active.loc[singleton.index[singleton]] = False
    return sample.loc[active], sample.index[~active]


def add_residual_metrics(
    frame: pd.DataFrame,
    *,
    residual_col: str,
    prefix: str = "ie",
    classification_by: Sequence[str] = ("fiscal_year",),
) -> pd.DataFrame:
    """Add signed, absolute, quartile, and median residual metrics."""

    require_columns(
        frame, (residual_col, *classification_by), context="residual metrics"
    )
    result = frame.copy()
    residual = numeric(result[residual_col])
    absolute = residual.abs()
    result[f"{prefix}_inefficiency"] = absolute
    result[f"{prefix}_efficiency"] = -absolute
    result[f"{prefix}_overinvestment"] = residual.clip(lower=0.0)
    result[f"{prefix}_underinvestment"] = (-residual).clip(lower=0.0)
    result[f"{prefix}_overinvestment_indicator"] = residual.gt(0).astype(float).where(
        residual.notna()
    )
    result[f"{prefix}_underinvestment_indicator"] = residual.lt(0).astype(float).where(
        residual.notna()
    )

    if classification_by:
        rank = result.groupby(
            list(classification_by), sort=False, dropna=True
        )[residual_col].transform(rank_zero_one)
        median_abs = result.groupby(
            list(classification_by), sort=False, dropna=True
        )[f"{prefix}_inefficiency"].transform("median")
    else:
        rank = rank_zero_one(residual)
        median_abs = pd.Series(absolute.median(), index=result.index)
    result[f"{prefix}_residual_rank"] = rank
    valid_classification = residual.notna() & rank.notna() & median_abs.notna()
    result[f"{prefix}_residual_group"] = pd.Series(
        np.select(
            [rank.le(0.25), rank.ge(0.75)],
            ["under", "over"],
            default="benchmark",
        ),
        index=result.index,
        dtype="string",
    ).where(valid_classification)
    result[f"{prefix}_efficient_below_median"] = absolute.lt(median_abs).astype(
        float
    ).where(valid_classification)
    return result


def fit_expected_investment(
    frame: pd.DataFrame,
    *,
    outcome: str,
    predictors: Sequence[str],
    group_cols: Sequence[str] = (),
    fixed_effects: Sequence[str] = (),
    min_obs: int = 20,
    min_residual_df: int = 1,
    rank_within_group: bool = False,
    absorb_fixed_effects: bool = False,
    specification: str = "custom",
    prefix: str = "ie",
    classification_by: Sequence[str] = ("fiscal_year",),
) -> ExpectedInvestmentResult:
    """Estimate expected investment by cell or in a pooled fixed-effect model.

    The returned diagnostic table records skipped cells, residual degrees of
    freedom, rank deficiency, model rank, and fit. Rank-deficient cells are
    estimated with the Moore-Penrose least-squares solution and explicitly
    flagged. ``absorb_fixed_effects=True`` uses a one-way within transformation
    instead of materializing a potentially large dummy matrix.
    """

    if min_obs < 2:
        raise ValueError("min_obs must be at least two")
    if min_residual_df < 1:
        raise ValueError("min_residual_df must be at least one")
    if absorb_fixed_effects and len(fixed_effects) != 1:
        raise ValueError(
            "absorb_fixed_effects=True requires exactly one fixed-effect column"
        )
    required = (outcome, *predictors, *group_cols, *fixed_effects)
    require_columns(frame, required, context="expected-investment model")
    if not frame.index.is_unique:
        raise ValueError("expected-investment model requires a unique DataFrame index")
    result = frame.copy()
    expected_col = f"{prefix}_expected"
    residual_col = f"{prefix}_residual"
    model_outcome_col = f"{prefix}_model_outcome"
    missing_input_col = f"{prefix}_missing_model_input"
    missing_group_col = f"{prefix}_missing_model_group"
    singleton_col = f"{prefix}_fixed_effect_singleton"
    result[expected_col] = np.nan
    result[residual_col] = np.nan
    result[model_outcome_col] = np.nan
    numeric_inputs = pd.DataFrame(
        {column: numeric(result[column]) for column in (outcome, *predictors)},
        index=result.index,
    )
    missing_inputs = numeric_inputs.isna().any(axis=1)
    if fixed_effects:
        missing_inputs |= result[list(fixed_effects)].isna().any(axis=1)
    result[missing_input_col] = missing_inputs
    if group_cols:
        missing_groups = result[list(group_cols)].isna().any(axis=1)
    else:
        missing_groups = pd.Series(False, index=result.index)
    result[missing_group_col] = missing_groups
    result[singleton_col] = False
    coefficient_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []

    if group_cols:
        group_key: str | list[str] = (
            group_cols[0] if len(group_cols) == 1 else list(group_cols)
        )
        grouped = result.loc[~missing_groups].groupby(
            group_key, sort=False, dropna=True
        )
        iterator = grouped
        if missing_groups.any():
            diagnostic_rows.append(
                {
                    **{column: pd.NA for column in group_cols},
                    "status": "missing_group_key",
                    "n": int(missing_groups.sum()),
                    "rank": 0,
                    "parameters": 0,
                    "residual_df": np.nan,
                    "rank_deficient": False,
                    "singleton_fixed_effect_n": 0,
                    "fixed_effect_method": "none",
                    "r2": np.nan,
                    "adj_r2": np.nan,
                }
            )
    else:
        iterator = [("__pooled__", result)]

    for key, grouped_cell in iterator:
        cell = grouped_cell.copy()
        model_columns = [outcome, *predictors, *fixed_effects]
        for column in (outcome, *predictors):
            cell[column] = numeric(cell[column])
        cell = cell.dropna(subset=model_columns)
        cell, singleton_index = _remove_fixed_effect_singletons(cell, fixed_effects)
        result.loc[singleton_index, singleton_col] = True
        singleton_n = int(len(singleton_index))
        key_tuple = key if isinstance(key, tuple) else (key,)
        key_values = (
            dict(zip(group_cols, key_tuple, strict=True)) if group_cols else {}
        )
        estimation = cell.copy()
        if rank_within_group:
            for column in (outcome, *predictors):
                estimation[column] = rank_zero_one(estimation[column])
        y = numeric(estimation[outcome])
        result.loc[estimation.index, model_outcome_col] = y

        if len(estimation) < min_obs:
            diagnostic_rows.append(
                {
                    **key_values,
                    "status": "small_cell",
                    "n": int(len(estimation)),
                    "rank": 0,
                    "parameters": 0,
                    "residual_df": np.nan,
                    "rank_deficient": False,
                    "singleton_fixed_effect_n": singleton_n,
                    "fixed_effect_method": (
                        "absorbed"
                        if absorb_fixed_effects
                        else ("dummy" if fixed_effects else "none")
                    ),
                    "r2": np.nan,
                    "adj_r2": np.nan,
                }
            )
            continue

        if absorb_fixed_effects:
            fixed_effect = fixed_effects[0]
            predictor_frame = estimation[list(predictors)].apply(numeric)
            fixed_group = estimation[fixed_effect]
            within_y = y - y.groupby(fixed_group, sort=False).transform("mean")
            within_x = predictor_frame - predictor_frame.groupby(
                fixed_group, sort=False
            ).transform("mean")
            x = within_x.to_numpy(dtype=float)
            within_rank = int(np.linalg.matrix_rank(x))
            fixed_effect_levels = int(fixed_group.nunique())
            rank = fixed_effect_levels + within_rank
            parameters = fixed_effect_levels + len(predictors)
            design_terms = list(predictors)
            fixed_effect_method = "absorbed"
        else:
            design = _design_matrix(
                estimation, predictors=predictors, fixed_effects=fixed_effects
            )
            x = design.to_numpy(dtype=float)
            rank = int(np.linalg.matrix_rank(x))
            parameters = int(x.shape[1])
            design_terms = list(design.columns)
            fixed_effect_method = "dummy" if fixed_effects else "none"

        nobs = int(len(estimation))
        degrees = nobs - rank
        if degrees < min_residual_df:
            diagnostic_rows.append(
                {
                    **key_values,
                    "status": "insufficient_residual_df",
                    "n": nobs,
                    "rank": rank,
                    "parameters": parameters,
                    "residual_df": degrees,
                    "rank_deficient": rank < parameters,
                    "singleton_fixed_effect_n": singleton_n,
                    "fixed_effect_method": fixed_effect_method,
                    "r2": np.nan,
                    "adj_r2": np.nan,
                }
            )
            continue

        if absorb_fixed_effects:
            beta, *_ = np.linalg.lstsq(
                x, within_y.to_numpy(dtype=float), rcond=None
            )
            fitted = y.groupby(fixed_group, sort=False).transform("mean") + pd.Series(
                x @ beta, index=estimation.index
            )
        else:
            beta, *_ = np.linalg.lstsq(x, y.to_numpy(dtype=float), rcond=None)
            fitted = pd.Series(x @ beta, index=estimation.index)
        residual = y - fitted
        result.loc[estimation.index, expected_col] = fitted
        result.loc[estimation.index, residual_col] = residual

        ssr = float((residual**2).sum())
        sst = float(((y - y.mean()) ** 2).sum())
        r2 = 1.0 - ssr / sst if sst > 0 else np.nan
        adj_r2 = (
            1.0 - (1.0 - r2) * (nobs - 1) / degrees
            if np.isfinite(r2) and degrees > 0
            else np.nan
        )
        diagnostic_rows.append(
            {
                **key_values,
                "status": "estimated",
                "n": nobs,
                "rank": rank,
                "parameters": parameters,
                "residual_df": degrees,
                "rank_deficient": rank < parameters,
                "singleton_fixed_effect_n": singleton_n,
                "fixed_effect_method": fixed_effect_method,
                "r2": r2,
                "adj_r2": adj_r2,
            }
        )
        for term, estimate in zip(design_terms, beta, strict=True):
            coefficient_rows.append(
                {
                    **key_values,
                    "term": term,
                    "estimate": float(estimate),
                    "n": nobs,
                    "fixed_effect_method": fixed_effect_method,
                }
            )

    result = add_residual_metrics(
        result,
        residual_col=residual_col,
        prefix=prefix,
        classification_by=classification_by,
    )
    coefficient_columns = [
        *group_cols,
        "term",
        "estimate",
        "n",
        "fixed_effect_method",
    ]
    diagnostic_columns = [
        *group_cols,
        "status",
        "n",
        "rank",
        "parameters",
        "residual_df",
        "rank_deficient",
        "singleton_fixed_effect_n",
        "fixed_effect_method",
        "r2",
        "adj_r2",
    ]
    return ExpectedInvestmentResult(
        panel=result,
        coefficients=pd.DataFrame(coefficient_rows, columns=coefficient_columns),
        diagnostics=pd.DataFrame(diagnostic_rows, columns=diagnostic_columns),
        specification=specification,
    )


def _require_model_keys(
    frame: pd.DataFrame,
    *,
    industry_col: str,
    period_col: str,
) -> None:
    require_columns(frame, (industry_col, period_col), context="model keys")


def estimate_bhv_2009(
    frame: pd.DataFrame,
    *,
    outcome: str = "ie_inv_bhv_total",
    sales_growth: str = "ie_sales_growth_lag",
    industry_col: str = "industry",
    period_col: str = "fiscal_year",
    min_obs: int = 20,
    min_residual_df: int = 1,
) -> ExpectedInvestmentResult:
    """Estimate the Biddle-Hilary-Verdi (2009) sales-growth model."""

    _require_model_keys(frame, industry_col=industry_col, period_col=period_col)
    return fit_expected_investment(
        frame,
        outcome=outcome,
        predictors=(sales_growth,),
        group_cols=(industry_col, period_col),
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        specification="bhv2009",
        classification_by=(period_col,),
    )


def estimate_enomoto_2024(
    frame: pd.DataFrame,
    *,
    outcome: str = "ie_inv_enomoto_ppe",
    sales_growth: str = "ie_sales_growth_lag",
    industry_col: str = "industry",
    period_col: str = "fiscal_year",
    min_obs: int = 20,
    min_residual_df: int = 1,
) -> ExpectedInvestmentResult:
    """Estimate the Japan-specific PPE residual model used by Enomoto et al."""

    _require_model_keys(frame, industry_col=industry_col, period_col=period_col)
    return fit_expected_investment(
        frame,
        outcome=outcome,
        predictors=(sales_growth,),
        group_cols=(industry_col, period_col),
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        specification="enomoto2024",
        classification_by=(period_col,),
    )


def estimate_bh_2006_q_cash_flow(
    frame: pd.DataFrame,
    *,
    outcome: str = "ie_inv_bh_fixed_assets",
    cash_flow_col: str = "ie_cash_flow_net_capital",
    q_col: str = "ie_tobin_q_lag",
    firm_col: str = "firm",
    group_cols: Sequence[str] = ("country",),
    min_obs: int = 20,
    min_residual_df: int = 1,
    period_col: str = "fiscal_year",
    transform_like_paper: bool = True,
) -> ExpectedInvestmentResult:
    """Estimate Biddle-Hilary cross-country investment-CF regressions.

    The coefficient on ``cash_flow_col`` in ``coefficients`` is the sensitivity
    measure. The published cross-country design applies arctangent transforms to
    investment and cash flow, logs the Q proxy, and includes firm fixed effects.
    Pass ``transform_like_paper=False`` for already transformed inputs.
    """

    require_columns(
        frame,
        (outcome, cash_flow_col, q_col, firm_col, period_col, *group_cols),
        context="Biddle-Hilary model",
    )
    work = frame.copy()
    model_outcome = outcome
    model_cash_flow = cash_flow_col
    model_q = q_col
    if transform_like_paper:
        model_outcome = "ie_bh_investment_atan"
        model_cash_flow = "ie_bh_cash_flow_atan"
        model_q = "ie_bh_q_log"
        work[model_outcome] = np.arctan(numeric(work[outcome]))
        work[model_cash_flow] = np.arctan(numeric(work[cash_flow_col]))
        q = numeric(work[q_col])
        work[model_q] = np.log(q.where(q.gt(0)))
    return fit_expected_investment(
        work,
        outcome=model_outcome,
        predictors=(model_cash_flow, model_q),
        group_cols=group_cols,
        fixed_effects=(firm_col,),
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        absorb_fixed_effects=True,
        specification="bh2006_q_cashflow",
        classification_by=(period_col,),
    )


def estimate_chen_2011(
    frame: pd.DataFrame,
    *,
    outcome: str = "ie_inv_bhv_total",
    sales_growth: str = "ie_sales_growth_lag",
    industry_col: str = "industry",
    period_col: str = "fiscal_year",
    min_obs: int = 20,
    min_residual_df: int = 1,
) -> ExpectedInvestmentResult:
    """Estimate the asymmetric-sales-growth model used by Chen et al. (2011)."""

    _require_model_keys(frame, industry_col=industry_col, period_col=period_col)
    work = frame.copy()
    growth = numeric(work[sales_growth])
    work["ie_negative_sales_growth"] = growth.lt(0).astype(float).where(
        growth.notna()
    )
    work["ie_negative_x_sales_growth"] = (
        work["ie_negative_sales_growth"] * growth
    )
    return fit_expected_investment(
        work,
        outcome=outcome,
        predictors=(
            "ie_negative_sales_growth",
            sales_growth,
            "ie_negative_x_sales_growth",
        ),
        group_cols=(industry_col, period_col),
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        specification="chen2011",
        classification_by=(period_col,),
    )


def estimate_richardson_2006(
    frame: pd.DataFrame,
    *,
    outcome: str = "ie_inv_richardson_new",
    growth_opportunities: str = "ie_value_to_price_lag",
    industry_col: str = "industry",
    period_col: str = "fiscal_year",
    min_obs: int = 20,
    min_residual_df: int = 1,
) -> ExpectedInvestmentResult:
    """Estimate Richardson's pooled expected-new-investment model."""

    predictors = (
        growth_opportunities,
        "ie_leverage_capital_lag",
        "ie_cash_assets_lag",
        "ie_firm_age_log_lag",
        "ie_size_log_assets_lag",
        "ie_stock_return_lag",
        "ie_inv_richardson_new_lag",
    )
    _require_model_keys(frame, industry_col=industry_col, period_col=period_col)
    return fit_expected_investment(
        frame,
        outcome=outcome,
        predictors=predictors,
        fixed_effects=(industry_col, period_col),
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        specification="richardson2006",
        classification_by=(period_col,),
    )


def _prepare_ranked_mcnichols_inputs(
    frame: pd.DataFrame,
    *,
    outcome: str,
    q_col: str,
    cash_flow_col: str,
    group_cols: Sequence[str],
    augmented: bool,
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Rank complete-case MS variables, then construct Q spline terms."""

    result = frame.copy()
    continuous = [outcome, q_col, cash_flow_col]
    if augmented:
        continuous.extend(("ie_asset_growth_log_lag", "ie_inv_ms_capex_lag"))
    continuous = list(dict.fromkeys(continuous))
    require_columns(
        result,
        (*continuous, *group_cols),
        context="McNichols-Stubben rank inputs",
    )
    if not result.index.is_unique:
        raise ValueError("McNichols-Stubben model requires a unique DataFrame index")

    originals = {column: result[column].copy() for column in continuous}
    numeric_source = pd.DataFrame(
        {column: numeric(frame[column]) for column in continuous}, index=frame.index
    )
    complete = numeric_source.notna().all(axis=1)
    complete &= ~frame[list(group_cols)].isna().any(axis=1)
    for column in continuous:
        result[column] = np.nan

    audit_names = {
        outcome: "ie_ms_outcome_rank",
        q_col: "ie_ms_q_rank",
        cash_flow_col: "ie_ms_cash_flow_rank",
    }
    if augmented:
        audit_names["ie_asset_growth_log_lag"] = "ie_ms_asset_growth_rank"
        audit_names["ie_inv_ms_capex_lag"] = "ie_ms_lagged_investment_rank"
    for audit_name in audit_names.values():
        result[audit_name] = np.nan
    if augmented:
        for number in (2, 3, 4):
            result[f"ie_q_q{number}"] = np.nan
            result[f"ie_q_x_q{number}"] = np.nan

    eligible = frame.loc[complete]
    for _, cell in eligible.groupby(list(group_cols), sort=False, dropna=True):
        index = cell.index
        ranked = {
            column: rank_zero_one(numeric_source.loc[index, column])
            for column in continuous
        }
        for column, values in ranked.items():
            result.loc[index, column] = values
            result.loc[index, audit_names[column]] = values
        if augmented:
            q_rank = ranked[q_col]
            quartile = np.floor(q_rank.mul(4)).clip(upper=3).add(1)
            for number in (2, 3, 4):
                indicator = quartile.eq(number).astype(float).where(q_rank.notna())
                result.loc[index, f"ie_q_q{number}"] = indicator
                result.loc[index, f"ie_q_x_q{number}"] = q_rank * indicator
    return result, originals


def estimate_mcnichols_stubben_2008(
    frame: pd.DataFrame,
    *,
    augmented: bool = False,
    outcome: str = "ie_inv_ms_capex",
    q_col: str = "ie_tobin_q_ms_lag",
    cash_flow_col: str = "ie_cash_flow_ms_net_capital",
    industry_col: str = "industry",
    period_col: str = "fiscal_year",
    min_obs: int = 20,
    min_residual_df: int = 1,
) -> ExpectedInvestmentResult:
    """Estimate the ranked McNichols-Stubben Q model by industry-year."""

    group_cols = (industry_col, period_col)
    _require_model_keys(frame, industry_col=industry_col, period_col=period_col)
    predictors: tuple[str, ...] = (q_col, cash_flow_col)
    specification = "mcnichols_stubben2008_basic"
    if augmented:
        predictors = (
            q_col,
            "ie_q_q2",
            "ie_q_q3",
            "ie_q_q4",
            "ie_q_x_q2",
            "ie_q_x_q3",
            "ie_q_x_q4",
            cash_flow_col,
            "ie_asset_growth_log_lag",
            "ie_inv_ms_capex_lag",
        )
        specification = "mcnichols_stubben2008_augmented"
    work, originals = _prepare_ranked_mcnichols_inputs(
        frame,
        outcome=outcome,
        q_col=q_col,
        cash_flow_col=cash_flow_col,
        group_cols=group_cols,
        augmented=augmented,
    )
    fitted = fit_expected_investment(
        work,
        outcome=outcome,
        predictors=predictors,
        group_cols=group_cols,
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        specification=specification,
        classification_by=(period_col,),
    )
    panel = fitted.panel.copy()
    for column, values in originals.items():
        panel[column] = values
    return ExpectedInvestmentResult(
        panel=panel,
        coefficients=fitted.coefficients,
        diagnostics=fitted.diagnostics,
        specification=fitted.specification,
    )
