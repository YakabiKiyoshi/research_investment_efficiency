from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from investment_efficiency import (
    CapitalColumns,
    add_capital_investment_inputs,
    add_interaction,
    add_overinvestment_likelihood,
    cash_flow_sensitivity_index,
    ohlson_value_to_price,
)


def capital_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "firm": ["A", "A", "A"],
            "fiscal_year": [2020, 2021, 2022],
            "industry": ["M", "M", "M"],
            "assets": [100.0, 120.0, 150.0],
            "sales": [80.0, 100.0, 120.0],
            "ppe": [40.0, 50.0, 65.0],
            "capex": [10.0, 12.0, 15.0],
            "rd": [1.0, np.nan, 2.0],
            "acquisitions": [2.0, 0.0, 1.0],
            "sale_ppe": [1.0, 0.0, 2.0],
            "depreciation": [4.0, 5.0, 6.0],
            "operating_cash_flow": [8.0, 10.0, 12.0],
            "net_income": [5.0, 7.0, 9.0],
            "cash": [10.0, 12.0, 15.0],
            "debt_current": [5.0, 6.0, 7.0],
            "debt_long": [20.0, 22.0, 25.0],
            "book_equity": [50.0, 60.0, 70.0],
            "market_equity": [90.0, 100.0, 130.0],
            "stock_return": [0.05, 0.10, -0.02],
            "listing_year": [2010, 2010, 2010],
            "operating_income_after_depreciation": [10.0, 12.0, 14.0],
            "dividends": [1.0, 1.0, 2.0],
        }
    )


class CapitalMeasureTests(unittest.TestCase):
    def test_published_investment_flow_definitions(self) -> None:
        result = add_capital_investment_inputs(capital_panel())
        row = result.iloc[1]
        self.assertAlmostEqual(row["ie_inv_bhv_total"], 12.0 / 100.0)
        self.assertAlmostEqual(row["ie_inv_richardson_new"], 7.0 / 110.0)
        self.assertAlmostEqual(row["ie_inv_enomoto_ppe"], 15.0 / 100.0)
        self.assertAlmostEqual(row["ie_inv_bh_fixed_assets"], 15.0 / 40.0)
        self.assertAlmostEqual(row["ie_inv_ms_capex"], 12.0 / 40.0)
        self.assertAlmostEqual(row["ie_asset_growth_log"], np.log(1.2))
        self.assertAlmostEqual(
            row["ie_market_leverage_long_debt"], 22.0 / 122.0
        )
        self.assertAlmostEqual(
            row["ie_market_leverage_total_debt"], 28.0 / 128.0
        )
        self.assertAlmostEqual(row["ie_cash_flow_ms_net_capital"], 10.0 / 40.0)
        self.assertAlmostEqual(row["ie_tobin_q_ms"], 160.0 / 120.0)
        self.assertTrue(row["ie_missing_rd"])
        self.assertAlmostEqual(row["ie_sales_growth"], 0.25)

    def test_propagate_policy_does_not_silently_zero_missing_rd(self) -> None:
        result = add_capital_investment_inputs(
            capital_panel(), missing_components="propagate"
        )
        self.assertTrue(np.isnan(result.loc[1, "ie_inv_bhv_total"]))

    def test_unavailable_depreciation_does_not_redefine_measures(self) -> None:
        result = add_capital_investment_inputs(
            capital_panel().drop(columns="depreciation")
        )
        self.assertTrue(result["ie_source_unavailable_depreciation"].all())
        self.assertTrue(result["ie_inv_richardson_new"].isna().all())
        self.assertTrue(result["ie_inv_enomoto_ppe"].isna().all())
        self.assertTrue(result["ie_inv_bh_fixed_assets"].isna().all())
        self.assertAlmostEqual(result.loc[1, "ie_inv_bhv_total"], 0.12)

    def test_row_missing_depreciation_can_still_use_zero_policy(self) -> None:
        frame = capital_panel()
        frame.loc[1, "depreciation"] = np.nan
        result = add_capital_investment_inputs(frame)
        self.assertFalse(result["ie_source_unavailable_depreciation"].any())
        self.assertTrue(result.loc[1, "ie_missing_depreciation"])
        self.assertAlmostEqual(result.loc[1, "ie_inv_enomoto_ppe"], 0.10)

    def test_row_missing_dividend_is_zero_with_audit_flag(self) -> None:
        frame = capital_panel()
        frame.loc[1, "dividends"] = np.nan
        result = add_capital_investment_inputs(frame)
        expected = ohlson_value_to_price(
            pd.Series([60.0]),
            pd.Series([12.0]),
            pd.Series([0.0]),
            pd.Series([100.0]),
        ).iloc[0]
        self.assertTrue(result.loc[1, "ie_missing_dividends"])
        self.assertFalse(result.loc[1, "ie_source_unavailable_dividends"])
        self.assertAlmostEqual(result.loc[1, "ie_value_to_price"], expected)

    def test_unavailable_dividend_source_remains_missing(self) -> None:
        result = add_capital_investment_inputs(
            capital_panel().drop(columns="dividends")
        )
        self.assertTrue(result["ie_source_unavailable_dividends"].all())
        self.assertTrue(result["ie_value_to_price"].isna().all())

    def test_lagged_measures_do_not_cross_year_gap(self) -> None:
        frame = capital_panel().iloc[[0, 2]].reset_index(drop=True)
        result = add_capital_investment_inputs(frame)
        self.assertTrue(np.isnan(result.loc[1, "ie_inv_bhv_total"]))
        self.assertTrue(np.isnan(result.loc[1, "ie_sales_growth"]))

    def test_source_columns_can_be_mapped_without_renaming(self) -> None:
        frame = capital_panel().rename(
            columns={"firm": "gvkey", "fiscal_year": "fyear", "assets": "at", "sales": "sale"}
        )
        result = add_capital_investment_inputs(
            frame,
            columns=CapitalColumns(
                firm="gvkey", period="fyear", assets="at", sales="sale"
            ),
        )
        self.assertAlmostEqual(result.loc[1, "ie_inv_bhv_total"], 0.12)

    def test_optional_debt_columns_can_be_omitted(self) -> None:
        result = add_capital_investment_inputs(
            capital_panel().drop(columns=["debt_current", "debt_long"]),
            columns=CapitalColumns(debt_current=None, debt_long=None),
        )
        self.assertTrue(result["ie_market_leverage_long_debt"].isna().all())

    def test_unavailable_one_sided_debt_does_not_become_zero(self) -> None:
        result = add_capital_investment_inputs(
            capital_panel().drop(columns="debt_current")
        )
        self.assertTrue(result["ie_source_unavailable_debt_current"].all())
        self.assertTrue(result["ie_leverage_capital"].isna().all())
        self.assertTrue(result["ie_market_leverage_total_debt"].isna().all())
        self.assertAlmostEqual(
            result.loc[1, "ie_market_leverage_long_debt"], 22.0 / 122.0
        )

    def test_ohlson_value_to_price_matches_formula(self) -> None:
        result = ohlson_value_to_price(
            pd.Series([50.0]),
            pd.Series([10.0]),
            pd.Series([1.0]),
            pd.Series([100.0]),
        )
        alpha = 0.62 / (1.12 - 0.62)
        expected = ((1 - alpha * 0.12) * 50 + alpha * 1.12 * 10 - alpha * 0.12) / 100
        self.assertAlmostEqual(result.iloc[0], expected)

    def test_overinvestment_score_uses_cash_and_inverse_leverage(self) -> None:
        frame = pd.DataFrame(
            {
                "year": [2020] * 4,
                "cash": [1.0, 2.0, 3.0, 4.0],
                "lev": [4.0, 3.0, 2.0, 1.0],
            }
        )
        result = add_overinvestment_likelihood(
            frame,
            cash_col="cash",
            leverage_col="lev",
            period_col="year",
            ntiles=2,
        )
        self.assertEqual(result.loc[0, "ie_overinvestment_likelihood"], 0.0)
        self.assertEqual(result.loc[3, "ie_overinvestment_likelihood"], 1.0)

    def test_overinvestment_default_uses_ten_tiles(self) -> None:
        frame = pd.DataFrame(
            {
                "year": [2020] * 10,
                "cash": np.arange(10, dtype=float),
                "lev": np.arange(9, -1, -1, dtype=float),
            }
        )
        result = add_overinvestment_likelihood(
            frame, cash_col="cash", leverage_col="lev", period_col="year"
        )
        np.testing.assert_allclose(
            result["ie_overinvestment_likelihood"], np.arange(10) / 9
        )

    def test_cash_flow_sensitivity_index(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": [1, 1, 1],
                "year": [1, 2, 3],
                "investment": [1.0, 2.0, 3.0],
                "cash_flow": [1.0, 2.0, 3.0],
            }
        )
        result = cash_flow_sensitivity_index(
            frame,
            firm_col="firm",
            period_col="year",
            investment_col="investment",
            cash_flow_col="cash_flow",
            window=3,
        )
        self.assertTrue(result.iloc[:2].isna().all())
        self.assertAlmostEqual(result.iloc[2], 14.0 / 6.0 - 2.0)

    def test_cfsi_clips_negative_cash_flow_and_rejects_zero_sum(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": [1, 1, 1, 2, 2, 2],
                "year": [1, 2, 3, 1, 2, 3],
                "investment": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
                "cash_flow": [-10.0, 0.0, 3.0, -1.0, 0.0, -2.0],
            }
        )
        result = cash_flow_sensitivity_index(
            frame,
            firm_col="firm",
            period_col="year",
            investment_col="investment",
            cash_flow_col="cash_flow",
            window=3,
        )
        self.assertAlmostEqual(result.iloc[2], 1.0)
        self.assertTrue(np.isnan(result.iloc[5]))

    def test_cfsi_can_lag_cash_flow(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": [1, 1, 1, 1],
                "year": [1, 2, 3, 4],
                "investment": [1.0, 2.0, 3.0, 4.0],
                "cash_flow": [1.0, 2.0, 3.0, 4.0],
            }
        )
        result = cash_flow_sensitivity_index(
            frame,
            firm_col="firm",
            period_col="year",
            investment_col="investment",
            cash_flow_col="cash_flow",
            window=2,
            lag_cash_flow=True,
        )
        self.assertAlmostEqual(result.iloc[2], 8.0 / 3.0 - 2.5)

    def test_cfsi_rejects_gap_spanning_window_unless_allowed(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": [1, 1, 1, 1],
                "year": [1, 2, 3, 5],
                "investment": [1.0, 2.0, 3.0, 4.0],
                "cash_flow": [1.0, 2.0, 3.0, 4.0],
            }
        )
        strict = cash_flow_sensitivity_index(
            frame,
            firm_col="firm",
            period_col="year",
            investment_col="investment",
            cash_flow_col="cash_flow",
            window=3,
        )
        allowed = cash_flow_sensitivity_index(
            frame,
            firm_col="firm",
            period_col="year",
            investment_col="investment",
            cash_flow_col="cash_flow",
            window=3,
            require_consecutive=False,
        )
        self.assertTrue(np.isnan(strict.iloc[3]))
        self.assertAlmostEqual(allowed.iloc[3], 29.0 / 9.0 - 3.0)

    def test_cfsi_rejects_interior_missing_year_in_valid_sample(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": [1, 1, 1],
                "year": [1, 2, 3],
                "investment": [1.0, np.nan, 3.0],
                "cash_flow": [1.0, 2.0, 3.0],
            }
        )
        result = cash_flow_sensitivity_index(
            frame,
            firm_col="firm",
            period_col="year",
            investment_col="investment",
            cash_flow_col="cash_flow",
            window=3,
            min_periods=2,
        )
        self.assertTrue(np.isnan(result.iloc[2]))

    def test_cfsi_requires_numeric_period_for_consecutive_windows(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": [1, 1],
                "year": ["FY1", "FY2"],
                "investment": [1.0, 2.0],
                "cash_flow": [1.0, 2.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "numeric annual period"):
            cash_flow_sensitivity_index(
                frame,
                firm_col="firm",
                period_col="year",
                investment_col="investment",
                cash_flow_col="cash_flow",
                window=2,
            )

    def test_add_interaction_preserves_missing_values(self) -> None:
        frame = pd.DataFrame({"x": [2.0, np.nan], "z": [3.0, 4.0]})
        result = add_interaction(frame, "x", "z", output_col="xz")
        self.assertEqual(result.loc[0, "xz"], 6.0)
        self.assertTrue(np.isnan(result.loc[1, "xz"]))


if __name__ == "__main__":
    unittest.main()
