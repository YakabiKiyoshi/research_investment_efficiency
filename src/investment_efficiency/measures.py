"""Investment-flow measures and conditioning variables from prior research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .panel import (
    numeric,
    panel_lag,
    rank_zero_one,
    require_columns,
    safe_divide,
    validate_panel,
)


MissingComponentPolicy = Literal["zero", "propagate"]


@dataclass(frozen=True)
class CapitalColumns:
    """Map a source panel to the package's capital-investment inputs."""

    firm: str = "firm"
    period: str = "fiscal_year"
    industry: str = "industry"
    assets: str = "assets"
    sales: str = "sales"
    ppe: str | None = "ppe"
    capex: str | None = "capex"
    rd: str | None = "rd"
    acquisitions: str | None = "acquisitions"
    sale_ppe: str | None = "sale_ppe"
    depreciation: str | None = "depreciation"
    operating_cash_flow: str | None = "operating_cash_flow"
    net_income: str | None = "net_income"
    cash: str | None = "cash"
    debt_current: str | None = "debt_current"
    debt_long: str | None = "debt_long"
    book_equity: str | None = "book_equity"
    market_equity: str | None = "market_equity"
    stock_return: str | None = "stock_return"
    listing_year: str | None = "listing_year"
    operating_income_after_depreciation: str | None = (
        "operating_income_after_depreciation"
    )
    dividends: str | None = "dividends"


def _optional(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return numeric(frame[column])


def _component(
    frame: pd.DataFrame,
    column: str | None,
    *,
    policy: MissingComponentPolicy,
    zero_when_unavailable: bool = True,
) -> tuple[pd.Series, pd.Series, bool]:
    values = _optional(frame, column)
    missing = values.isna()
    unavailable = (
        column is None or column not in frame or not bool(values.notna().any())
    )
    if policy == "zero" and (zero_when_unavailable or not unavailable):
        values = values.fillna(0.0)
    return values, missing, unavailable


def _at_least_one_present(frame: pd.DataFrame, columns: tuple[str | None, ...]) -> bool:
    return any(column is not None and column in frame for column in columns)


def ohlson_value_to_price(
    book_equity: pd.Series,
    operating_income_after_depreciation: pd.Series,
    dividends: pd.Series,
    market_equity: pd.Series,
    *,
    discount_rate: float = 0.12,
    persistence: float = 0.62,
) -> pd.Series:
    """Compute Richardson's Ohlson-based V/P growth-opportunity proxy."""

    if discount_rate <= 0:
        raise ValueError("discount_rate must be positive")
    if not 0 <= persistence < 1 + discount_rate:
        raise ValueError("persistence must be in [0, 1 + discount_rate)")
    alpha = persistence / (1.0 + discount_rate - persistence)
    value_assets_in_place = (
        (1.0 - alpha * discount_rate) * numeric(book_equity)
        + alpha * (1.0 + discount_rate) * numeric(operating_income_after_depreciation)
        - alpha * discount_rate * numeric(dividends)
    )
    return safe_divide(
        value_assets_in_place,
        market_equity,
        require_positive_denominator=True,
    )


def add_capital_investment_inputs(
    frame: pd.DataFrame,
    *,
    columns: CapitalColumns = CapitalColumns(),
    missing_components: MissingComponentPolicy = "zero",
    missing_dividends: MissingComponentPolicy = "zero",
    require_consecutive: bool = True,
) -> pd.DataFrame:
    """Construct canonical capital-investment measures and model inputs.

    Component items (R&D, acquisitions, PPE sales, and depreciation) are often
    reported as missing when economically zero. The default reproduces the
    common Compustat convention of replacing row-level missing components by
    zero, while retaining audit flags. A wholly unavailable depreciation source
    is never treated as zero because that would redefine three investment
    measures. Row-level missing dividends are controlled separately by
    ``missing_dividends`` and are zero by default when that source is available.
    Use ``propagate`` when missing does not reliably mean zero in the database.
    """

    if missing_components not in {"zero", "propagate"}:
        raise ValueError("missing_components must be 'zero' or 'propagate'")
    if missing_dividends not in {"zero", "propagate"}:
        raise ValueError("missing_dividends must be 'zero' or 'propagate'")
    require_columns(
        frame,
        (columns.firm, columns.period, columns.assets, columns.sales),
        context="capital panel",
    )
    validate_panel(frame, firm_col=columns.firm, period_col=columns.period)
    result = frame.copy()
    assets = numeric(result[columns.assets])
    sales = numeric(result[columns.sales])
    lag = lambda name: panel_lag(  # noqa: E731 - compact mapping helper
        result,
        name,
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    lag_assets = numeric(lag(columns.assets))
    lag_sales = numeric(lag(columns.sales))
    average_assets = assets.add(lag_assets).div(2.0)

    capex = _optional(result, columns.capex)
    ppe = _optional(result, columns.ppe)
    rd, missing_rd, unavailable_rd = _component(
        result, columns.rd, policy=missing_components
    )
    acquisitions, missing_acquisitions, unavailable_acquisitions = _component(
        result, columns.acquisitions, policy=missing_components
    )
    sale_ppe, missing_sale_ppe, unavailable_sale_ppe = _component(
        result, columns.sale_ppe, policy=missing_components
    )
    depreciation, missing_depreciation, unavailable_depreciation = _component(
        result,
        columns.depreciation,
        policy=missing_components,
        zero_when_unavailable=False,
    )
    result["ie_missing_rd"] = missing_rd
    result["ie_missing_acquisitions"] = missing_acquisitions
    result["ie_missing_sale_ppe"] = missing_sale_ppe
    result["ie_missing_depreciation"] = missing_depreciation
    result["ie_source_unavailable_rd"] = unavailable_rd
    result["ie_source_unavailable_acquisitions"] = unavailable_acquisitions
    result["ie_source_unavailable_sale_ppe"] = unavailable_sale_ppe
    result["ie_source_unavailable_depreciation"] = unavailable_depreciation

    total_expenditure = capex + rd + acquisitions - sale_ppe
    result["ie_inv_bhv_total"] = safe_divide(
        total_expenditure, lag_assets, require_positive_denominator=True
    )
    result["ie_inv_richardson_new"] = safe_divide(
        total_expenditure - depreciation,
        average_assets,
        require_positive_denominator=True,
    )
    lag_ppe = (
        numeric(lag(columns.ppe))
        if columns.ppe is not None and columns.ppe in result
        else pd.Series(np.nan, index=result.index, dtype=float)
    )
    result["ie_inv_enomoto_ppe"] = safe_divide(
        ppe - lag_ppe + depreciation,
        lag_assets,
        require_positive_denominator=True,
    )
    result["ie_inv_bh_fixed_assets"] = safe_divide(
        ppe - lag_ppe + depreciation,
        lag_ppe,
        require_positive_denominator=True,
    )
    result["ie_inv_ms_capex"] = safe_divide(
        capex, lag_ppe, require_positive_denominator=True
    )

    result["ie_sales_growth"] = safe_divide(
        sales - lag_sales, lag_sales, require_positive_denominator=True
    )
    result["ie_asset_growth"] = safe_divide(
        assets - lag_assets, lag_assets, require_positive_denominator=True
    )
    result["ie_asset_growth_log"] = np.log(
        safe_divide(assets, lag_assets, require_positive_denominator=True)
    )
    result["ie_size_log_assets"] = np.log(assets.where(assets.gt(0)))

    cfo = _optional(result, columns.operating_cash_flow)
    net_income = _optional(result, columns.net_income)
    result["ie_operating_cash_flow_assets"] = safe_divide(
        cfo, lag_assets, require_positive_denominator=True
    )
    result["ie_cash_flow_net_capital"] = safe_divide(
        net_income + depreciation,
        lag_ppe,
        require_positive_denominator=True,
    )
    result["ie_cash_flow_ms_net_capital"] = safe_divide(
        cfo,
        lag_ppe,
        require_positive_denominator=True,
    )

    cash = _optional(result, columns.cash)
    result["ie_cash_assets"] = safe_divide(
        cash, assets, require_positive_denominator=True
    )
    debt_columns = (columns.debt_current, columns.debt_long)
    if _at_least_one_present(result, debt_columns):
        (
            debt_current,
            result["ie_missing_debt_current"],
            unavailable_debt_current,
        ) = _component(
            result,
            columns.debt_current,
            policy=missing_components,
            zero_when_unavailable=False,
        )
        debt_long, result["ie_missing_debt_long"], unavailable_debt_long = _component(
            result,
            columns.debt_long,
            policy=missing_components,
            zero_when_unavailable=False,
        )
        debt = debt_current + debt_long
    else:
        debt_current = pd.Series(np.nan, index=result.index, dtype=float)
        debt_long = pd.Series(np.nan, index=result.index, dtype=float)
        debt = pd.Series(np.nan, index=result.index, dtype=float)
        result["ie_missing_debt_current"] = True
        result["ie_missing_debt_long"] = True
        unavailable_debt_current = True
        unavailable_debt_long = True
    result["ie_source_unavailable_debt_current"] = unavailable_debt_current
    result["ie_source_unavailable_debt_long"] = unavailable_debt_long
    book_equity = _optional(result, columns.book_equity)
    market_equity = _optional(result, columns.market_equity)
    result["ie_leverage_assets"] = safe_divide(
        debt, assets, require_positive_denominator=True
    )
    result["ie_leverage_capital"] = safe_divide(
        debt, debt + book_equity, require_positive_denominator=True
    )
    result["ie_market_leverage_long_debt"] = safe_divide(
        debt_long, debt_long + market_equity, require_positive_denominator=True
    )
    result["ie_market_leverage_total_debt"] = safe_divide(
        debt, debt + market_equity, require_positive_denominator=True
    )
    result["ie_tobin_q"] = safe_divide(
        market_equity + debt, assets, require_positive_denominator=True
    )
    result["ie_tobin_q_ms"] = safe_divide(
        market_equity + assets - book_equity,
        assets,
        require_positive_denominator=True,
    )
    result["ie_market_to_book"] = safe_divide(
        market_equity, book_equity, require_positive_denominator=True
    )

    stock_return = _optional(result, columns.stock_return)
    result["ie_stock_return"] = stock_return
    period = pd.to_numeric(result[columns.period], errors="coerce")
    if columns.listing_year is not None and columns.listing_year in result:
        listing_year = pd.to_numeric(result[columns.listing_year], errors="coerce")
        age_years = period - listing_year
        result["ie_age_uses_first_observation"] = False
    else:
        first_period = period.groupby(result[columns.firm], sort=False).transform("min")
        age_years = period - first_period
        result["ie_age_uses_first_observation"] = True
    result["ie_firm_age_log"] = np.log1p(age_years.where(age_years.ge(0)))

    op_income = _optional(result, columns.operating_income_after_depreciation)
    dividends, missing_dividends_flag, unavailable_dividends = _component(
        result,
        columns.dividends,
        policy=missing_dividends,
        zero_when_unavailable=False,
    )
    result["ie_missing_dividends"] = missing_dividends_flag
    result["ie_source_unavailable_dividends"] = unavailable_dividends
    result["ie_value_to_price"] = ohlson_value_to_price(
        book_equity,
        op_income,
        dividends,
        market_equity,
    )

    lag_targets = (
        "ie_sales_growth",
        "ie_asset_growth",
        "ie_asset_growth_log",
        "ie_size_log_assets",
        "ie_operating_cash_flow_assets",
        "ie_cash_flow_ms_net_capital",
        "ie_cash_assets",
        "ie_leverage_assets",
        "ie_leverage_capital",
        "ie_market_leverage_long_debt",
        "ie_market_leverage_total_debt",
        "ie_tobin_q",
        "ie_tobin_q_ms",
        "ie_market_to_book",
        "ie_stock_return",
        "ie_firm_age_log",
        "ie_value_to_price",
        "ie_inv_richardson_new",
        "ie_inv_ms_capex",
    )
    for target in lag_targets:
        result[f"{target}_lag"] = numeric(
            panel_lag(
                result,
                target,
                firm_col=columns.firm,
                period_col=columns.period,
                require_consecutive=require_consecutive,
            )
        )
    return result


def add_overinvestment_likelihood(
    frame: pd.DataFrame,
    *,
    cash_col: str = "ie_cash_assets",
    leverage_col: str = "ie_market_leverage_long_debt",
    period_col: str = "fiscal_year",
    output_col: str = "ie_overinvestment_likelihood",
    ntiles: int = 10,
) -> pd.DataFrame:
    """Add Biddle-et-al.'s ex-ante liquidity-based ``OverI`` score.

    The default leverage is long-term debt divided by long-term debt plus
    market equity. Japanese applications using total debt can pass
    ``ie_market_leverage_total_debt`` explicitly.
    """

    if ntiles < 2:
        raise ValueError("ntiles must be at least two")
    require_columns(
        frame, (cash_col, leverage_col, period_col), context="OverI inputs"
    )
    result = frame.copy()

    def tile(series: pd.Series) -> pd.Series:
        scaled = rank_zero_one(series)
        return np.floor(scaled.mul(ntiles)).clip(upper=ntiles - 1).div(ntiles - 1)

    cash_rank = result.groupby(period_col, sort=False, dropna=True)[cash_col].transform(
        tile
    )
    inverse_leverage_rank = result.groupby(
        period_col, sort=False, dropna=True
    )[leverage_col].transform(lambda values: tile(-numeric(values)))
    result[output_col] = cash_rank.add(inverse_leverage_rank).div(2.0)
    return result


def cash_flow_sensitivity_index(
    frame: pd.DataFrame,
    *,
    firm_col: str = "firm",
    period_col: str = "fiscal_year",
    investment_col: str = "ie_inv_ms_capex",
    cash_flow_col: str = "ie_cash_flow_net_capital",
    window: int = 10,
    min_periods: int | None = None,
    lag_cash_flow: bool = False,
    require_consecutive: bool = True,
) -> pd.Series:
    """Compute the rolling Hovakimian/Biddle-Hilary CFSI measure.

    CFSI is cash-flow-weighted average investment minus arithmetic average
    investment. Negative cash flows are set to zero before forming weights.
    """

    if window < 2:
        raise ValueError("window must be at least two")
    minimum = window if min_periods is None else min_periods
    if not 2 <= minimum <= window:
        raise ValueError("min_periods must be between two and window")
    require_columns(
        frame,
        (firm_col, period_col, investment_col, cash_flow_col),
        context="CFSI inputs",
    )
    validate_panel(frame, firm_col=firm_col, period_col=period_col)
    ordered = frame.sort_values([firm_col, period_col], kind="stable").copy()
    if require_consecutive:
        numeric_period = pd.to_numeric(ordered[period_col], errors="coerce")
        if numeric_period.isna().any():
            raise ValueError(
                "require_consecutive=True requires a numeric annual period column"
            )
        ordered["__numeric_period"] = numeric_period
    ordered["__investment"] = numeric(ordered[investment_col])
    ordered["__cash_flow"] = numeric(ordered[cash_flow_col])
    if lag_cash_flow:
        ordered["__cash_flow"] = panel_lag(
            ordered,
            "__cash_flow",
            firm_col=firm_col,
            period_col=period_col,
            require_consecutive=require_consecutive,
        )
    output = pd.Series(np.nan, index=ordered.index, dtype=float)
    for _, group in ordered.groupby(firm_col, sort=False):
        investment = group["__investment"]
        cash_flow = group["__cash_flow"]
        valid = investment.notna() & cash_flow.notna()
        positive_cash_flow = cash_flow.clip(lower=0.0).where(valid)
        count = valid.astype(float).rolling(window, min_periods=1).sum()
        denominator = positive_cash_flow.fillna(0.0).rolling(
            window, min_periods=1
        ).sum()
        weighted_sum = (positive_cash_flow * investment).fillna(0.0).rolling(
            window, min_periods=1
        ).sum()
        average_investment = investment.where(valid).rolling(
            window, min_periods=1
        ).mean()
        eligible = count.ge(minimum) & denominator.gt(0) & valid
        if require_consecutive:
            years = group["__numeric_period"].where(valid)
            first_year = years.rolling(window, min_periods=1).min()
            last_year = years.rolling(window, min_periods=1).max()
            eligible &= last_year.sub(first_year).add(1).eq(count)
        values = weighted_sum.div(denominator) - average_investment
        output.loc[group.index] = values.where(eligible)
    return output.reindex(frame.index)


def add_interaction(
    frame: pd.DataFrame,
    left: str,
    right: str,
    *,
    output_col: str | None = None,
) -> pd.DataFrame:
    """Add an explicitly named interaction for one-stage sensitivity models."""

    require_columns(frame, (left, right), context="interaction inputs")
    result = frame.copy()
    name = output_col or f"{left}_x_{right}"
    result[name] = numeric(result[left]) * numeric(result[right])
    return result
