from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from investment_efficiency import add_labor_investment_inputs, estimate_jlw_2014


class LaborInvestmentTests(unittest.TestCase):
    def test_labor_inputs_include_net_hiring_and_small_loss_bins(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": ["A", "A", "A"],
                "fiscal_year": [2020, 2021, 2022],
                "industry": ["M", "M", "M"],
                "employees": [100.0, 110.0, 99.0],
                "sales": [100.0, 120.0, 126.0],
                "assets": [100.0, 110.0, 120.0],
                "net_income": [-0.4, -0.25, 3.0],
                "stock_return": [0.1, 0.2, -0.1],
                "market_equity": [80.0, 90.0, 95.0],
                "quick_assets": [30.0, 32.0, 33.0],
                "current_liabilities": [20.0, 20.0, 22.0],
                "debt_current": [5.0, 6.0, 7.0],
                "debt_long": [10.0, 11.0, 12.0],
            }
        )
        result = add_labor_investment_inputs(frame)
        self.assertAlmostEqual(result.loc[1, "ie_labor_net_hire"], 0.10)
        self.assertAlmostEqual(result.loc[1, "ie_labor_sales_growth"], 0.20)
        self.assertEqual(result.loc[2, "ie_labor_sales_growth_lag"], 0.20)
        self.assertEqual(result.loc[2, "ie_labor_loss_bin1_lag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "ie_labor_delta_quick"], 1 / 15)
        self.assertAlmostEqual(result.loc[1, "ie_labor_leverage_lag"], 0.15)

    def test_full_jlw_estimator_produces_audited_outputs(self) -> None:
        rng = np.random.default_rng(9)
        n = 80
        predictor_names = [
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
        ]
        frame = pd.DataFrame(
            {
                "industry": np.where(np.arange(n) % 2, "A", "B"),
                "fiscal_year": np.where(np.arange(n) < n / 2, 2020, 2021),
            }
        )
        for name in predictor_names:
            frame[name] = rng.normal(size=n)
        frame["ie_labor_net_hire"] = (
            0.02
            + 0.3 * frame["ie_labor_sales_growth"]
            - 0.2 * frame["ie_labor_leverage_lag"]
            + rng.normal(scale=0.01, size=n)
        )
        result = estimate_jlw_2014(frame)
        self.assertEqual(result.specification, "jlw2014")
        self.assertTrue(result.panel["ie_labor_residual"].notna().all())
        self.assertTrue(
            result.panel["ie_labor_absolute_abnormal_net_hiring"].ge(0).all()
        )
        self.assertIn("ie_labor_inefficiency_type", result.panel)

    def test_raw_labor_panel_can_be_prepared_and_estimated_end_to_end(self) -> None:
        rng = np.random.default_rng(14)
        firms = np.repeat(np.arange(30), 4)
        years = np.tile(np.arange(2020, 2024), 30)
        trend = years - 2020
        raw = pd.DataFrame(
            {
                "firm": firms,
                "fiscal_year": years,
                "industry": np.where(firms % 2, "A", "B"),
                "employees": 100 + firms + 2 * trend + rng.normal(size=len(firms)),
                "sales": 150 + 2 * firms + 5 * trend + rng.normal(size=len(firms)),
                "assets": 200 + 3 * firms + 4 * trend + rng.normal(size=len(firms)),
                "net_income": rng.normal(2.0, 4.0, size=len(firms)),
                "stock_return": rng.normal(0.08, 0.2, size=len(firms)),
                "market_equity": 180 + 2 * firms + rng.uniform(1, 20, len(firms)),
                "quick_assets": 70 + firms + rng.uniform(1, 10, len(firms)),
                "current_liabilities": 40 + firms / 2 + rng.uniform(1, 5, len(firms)),
                "debt_current": 10 + rng.uniform(0, 5, len(firms)),
                "debt_long": 30 + rng.uniform(0, 10, len(firms)),
            }
        )
        prepared = add_labor_investment_inputs(raw)
        result = estimate_jlw_2014(prepared)
        final_year = result.panel["fiscal_year"].eq(2023)
        self.assertEqual(result.panel.loc[final_year, "ie_labor_residual"].notna().sum(), 30)
        self.assertIn("residual_df", result.diagnostics)


if __name__ == "__main__":
    unittest.main()
