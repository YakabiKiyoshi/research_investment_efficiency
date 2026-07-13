"""Labor-investment efficiency following Jung, Lee, and Weber (2014)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .models import ExpectedInvestmentResult, fit_expected_investment
from .panel import numeric, panel_lag, rank_zero_one, require_columns, safe_divide


@dataclass(frozen=True)
class LaborColumns:
    """Map a source panel to the Jung-Lee-Weber labor inputs."""

    firm: str = "firm"
    period: str = "fiscal_year"
    industry: str = "industry"
    employees: str = "employees"
    sales: str = "sales"
    assets: str = "assets"
    net_income: str = "net_income"
    stock_return: str = "stock_return"
    market_equity: str = "market_equity"
    quick_assets: str = "quick_assets"
    current_liabilities: str = "current_liabilities"
    debt_current: str = "debt_current"
    long_term_debt: str = "debt_long"


def add_labor_investment_inputs(
    frame: pd.DataFrame,
    *,
    columns: LaborColumns = LaborColumns(),
    require_consecutive: bool = True,
) -> pd.DataFrame:
    """Build the full expected-net-hiring inputs from JLW equation (1)."""

    required = (
        columns.firm,
        columns.period,
        columns.industry,
        columns.employees,
        columns.sales,
        columns.assets,
        columns.net_income,
        columns.stock_return,
        columns.market_equity,
        columns.quick_assets,
        columns.current_liabilities,
        columns.debt_current,
        columns.long_term_debt,
    )
    require_columns(frame, required, context="labor panel")
    result = frame.copy()

    def lag(column: str, periods: int = 1) -> pd.Series:
        return numeric(
            panel_lag(
                result,
                column,
                firm_col=columns.firm,
                period_col=columns.period,
                periods=periods,
                require_consecutive=require_consecutive,
            )
        )

    employees = numeric(result[columns.employees])
    sales = numeric(result[columns.sales])
    assets = numeric(result[columns.assets])
    lag_employees = lag(columns.employees)
    lag_sales = lag(columns.sales)
    lag_assets = lag(columns.assets)
    result["ie_labor_net_hire"] = safe_divide(
        employees - lag_employees,
        lag_employees,
        require_positive_denominator=True,
    )
    result["ie_labor_sales_growth"] = safe_divide(
        sales - lag_sales, lag_sales, require_positive_denominator=True
    )
    result["ie_labor_sales_growth_lag"] = panel_lag(
        result.assign(__growth=result["ie_labor_sales_growth"]),
        "__growth",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    result["ie_labor_roa"] = safe_divide(
        numeric(result[columns.net_income]),
        lag_assets,
        require_positive_denominator=True,
    )
    result["ie_labor_delta_roa"] = result["ie_labor_roa"] - panel_lag(
        result,
        "ie_labor_roa",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    result["ie_labor_delta_roa_lag"] = panel_lag(
        result,
        "ie_labor_delta_roa",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    result["ie_labor_return"] = numeric(result[columns.stock_return])
    lag_market_equity = lag(columns.market_equity)
    log_market_equity = np.log(lag_market_equity.where(lag_market_equity.gt(0)))
    result["ie_labor_size_rank_lag"] = log_market_equity.groupby(
        result[columns.period], sort=False
    ).transform(rank_zero_one)

    quick = safe_divide(
        numeric(result[columns.quick_assets]),
        numeric(result[columns.current_liabilities]),
        require_positive_denominator=True,
    )
    result["ie_labor_quick"] = quick
    result["ie_labor_quick_lag"] = panel_lag(
        result,
        "ie_labor_quick",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    result["ie_labor_delta_quick"] = safe_divide(
        quick - result["ie_labor_quick_lag"],
        result["ie_labor_quick_lag"],
        require_positive_denominator=True,
    )
    result["ie_labor_delta_quick_lag"] = panel_lag(
        result,
        "ie_labor_delta_quick",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    leverage = safe_divide(
        numeric(result[columns.debt_current])
        + numeric(result[columns.long_term_debt]),
        assets,
        require_positive_denominator=True,
    )
    result["ie_labor_leverage_lag"] = panel_lag(
        result.assign(__leverage=leverage),
        "__leverage",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )

    lag_roa = panel_lag(
        result,
        "ie_labor_roa",
        firm_col=columns.firm,
        period_col=columns.period,
        require_consecutive=require_consecutive,
    )
    for number in range(1, 6):
        upper = -0.005 * (number - 1)
        lower = -0.005 * number
        result[f"ie_labor_loss_bin{number}_lag"] = (
            numeric(lag_roa).ge(lower).astype(float)
            * numeric(lag_roa).lt(upper).astype(float)
        ).where(numeric(lag_roa).notna())
    return result


def _add_labor_categories(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    actual = numeric(result["ie_labor_net_hire"])
    residual = numeric(result["ie_labor_residual"])
    result["ie_labor_abnormal_net_hiring"] = residual
    result["ie_labor_absolute_abnormal_net_hiring"] = residual.abs()
    result["ie_labor_inefficiency_type"] = pd.Series(
        np.select(
            [
                residual.gt(0) & actual.ge(0),
                residual.gt(0) & actual.lt(0),
                residual.lt(0) & actual.ge(0),
                residual.lt(0) & actual.lt(0),
            ],
            ["over_hiring", "under_firing", "under_hiring", "over_firing"],
            default="on_expected",
        ),
        index=result.index,
        dtype="string",
    ).where(residual.notna())
    return result


def estimate_jlw_2014(
    frame: pd.DataFrame,
    *,
    industry_col: str = "industry",
    period_col: str = "fiscal_year",
    min_obs: int = 20,
    min_residual_df: int = 1,
) -> ExpectedInvestmentResult:
    """Estimate JLW expected net hiring with industry fixed effects."""

    predictors = (
        "ie_labor_sales_growth_lag",
        "ie_labor_sales_growth",
        "ie_labor_delta_roa",
        "ie_labor_delta_roa_lag",
        "ie_labor_roa",
        "ie_labor_return",
        "ie_labor_size_rank_lag",
        "ie_labor_quick_lag",
        "ie_labor_delta_quick_lag",
        "ie_labor_delta_quick",
        "ie_labor_leverage_lag",
        "ie_labor_loss_bin1_lag",
        "ie_labor_loss_bin2_lag",
        "ie_labor_loss_bin3_lag",
        "ie_labor_loss_bin4_lag",
        "ie_labor_loss_bin5_lag",
    )
    base = fit_expected_investment(
        frame,
        outcome="ie_labor_net_hire",
        predictors=predictors,
        fixed_effects=(industry_col,),
        min_obs=min_obs,
        min_residual_df=min_residual_df,
        specification="jlw2014",
        prefix="ie_labor",
        classification_by=(period_col,),
    )
    return ExpectedInvestmentResult(
        panel=_add_labor_categories(base.panel),
        coefficients=base.coefficients,
        diagnostics=base.diagnostics,
        specification=base.specification,
    )
