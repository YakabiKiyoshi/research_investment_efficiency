"""Panel-data validation and transformation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd


def require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    context: str = "data",
) -> None:
    """Raise a readable error when required columns are absent."""

    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{context} is missing required columns: {missing}")


def numeric(series: pd.Series) -> pd.Series:
    """Coerce a series to floating point, replacing infinities with missing."""

    return pd.to_numeric(series, errors="coerce").astype(float).replace(
        [np.inf, -np.inf], np.nan
    )


def safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    require_positive_denominator: bool = False,
) -> pd.Series:
    """Divide numeric series without returning infinities."""

    num = numeric(numerator)
    den = numeric(denominator)
    valid = den.gt(0) if require_positive_denominator else den.ne(0)
    return num.div(den.where(valid)).replace([np.inf, -np.inf], np.nan)


def validate_panel(frame: pd.DataFrame, *, firm_col: str, period_col: str) -> None:
    """Require a unique index and nonmissing, unique firm-period identifiers."""

    require_columns(frame, (firm_col, period_col), context="panel")
    if not frame.index.is_unique:
        raise ValueError("panel requires a unique DataFrame index")
    if frame[[firm_col, period_col]].isna().any().any():
        raise ValueError("firm and period identifiers must be non-missing")
    duplicated = frame.duplicated([firm_col, period_col], keep=False)
    if duplicated.any():
        examples = (
            frame.loc[duplicated, [firm_col, period_col]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"firm-period identifiers must be unique; examples: {examples}")


def panel_lag(
    frame: pd.DataFrame,
    column: str,
    *,
    firm_col: str,
    period_col: str,
    periods: int = 1,
    require_consecutive: bool = True,
) -> pd.Series:
    """Return a firm lag aligned to the original index.

    With ``require_consecutive=True``, ``period_col`` must be an integer-like
    annual index and lags crossing a calendar gap are set to missing.
    """

    if periods < 1:
        raise ValueError("periods must be at least one")
    require_columns(frame, (firm_col, period_col, column), context="panel lag")
    validate_panel(frame, firm_col=firm_col, period_col=period_col)
    ordered = frame.sort_values([firm_col, period_col], kind="stable")
    lagged = ordered.groupby(firm_col, sort=False)[column].shift(periods)
    if require_consecutive:
        period = pd.to_numeric(ordered[period_col], errors="coerce")
        if period.isna().any():
            raise ValueError(
                "require_consecutive=True requires a numeric annual period column"
            )
        lag_period = ordered.groupby(firm_col, sort=False)[period_col].shift(periods)
        lag_period = pd.to_numeric(lag_period, errors="coerce")
        lagged = lagged.where(period.sub(lag_period).eq(periods))
    return lagged.reindex(frame.index)


def winsorize(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    by: Sequence[str] = (),
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.DataFrame:
    """Winsorize selected columns, optionally within groups."""

    if not 0 <= lower < upper <= 1:
        raise ValueError("winsor limits must satisfy 0 <= lower < upper <= 1")
    require_columns(frame, (*columns, *by), context="winsorization")
    result = frame.copy()

    def clip_group(series: pd.Series) -> pd.Series:
        values = numeric(series)
        valid = values.dropna()
        if valid.empty:
            return values
        lo, hi = valid.quantile([lower, upper])
        return values.clip(lower=lo, upper=hi)

    for column in columns:
        if by:
            result[column] = result.groupby(
                list(by), sort=False, dropna=False
            )[column].transform(clip_group)
        else:
            result[column] = clip_group(result[column])
    return result


def rank_zero_one(series: pd.Series) -> pd.Series:
    """Rank nonmissing values to the closed interval [0, 1]."""

    values = numeric(series)
    count = int(values.notna().sum())
    if count == 0:
        return values
    if count == 1:
        return values.where(values.isna(), 0.5)
    ranks = values.rank(method="average", na_option="keep")
    return (ranks - 1.0) / (count - 1.0)
