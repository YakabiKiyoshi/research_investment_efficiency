from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from investment_efficiency import (
    add_residual_metrics,
    estimate_bh_2006_q_cash_flow,
    estimate_bhv_2009,
    estimate_chen_2011,
    estimate_enomoto_2024,
    estimate_mcnichols_stubben_2008,
    estimate_richardson_2006,
    fit_expected_investment,
)


class ExpectedInvestmentTests(unittest.TestCase):
    def test_cell_model_recovers_exact_linear_relation(self) -> None:
        x = np.linspace(-1, 1, 20)
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "x": x,
                "investment": 1.0 + 2.0 * x,
            }
        )
        result = fit_expected_investment(
            frame,
            outcome="investment",
            predictors=("x",),
            group_cols=("industry", "fiscal_year"),
            min_obs=20,
        )
        self.assertLess(result.panel["ie_residual"].abs().max(), 1e-12)
        self.assertEqual(result.diagnostics.loc[0, "status"], "estimated")
        self.assertAlmostEqual(
            result.coefficients.set_index("term").loc["x", "estimate"], 2.0
        )
        np.testing.assert_allclose(
            result.panel["ie_model_outcome"],
            result.panel["ie_expected"] + result.panel["ie_residual"],
        )

    def test_small_cell_is_preserved_and_flagged(self) -> None:
        frame = pd.DataFrame(
            {
                "industry": ["A"] * 3,
                "fiscal_year": [2020] * 3,
                "x": [1.0, 2.0, 3.0],
                "investment": [2.0, 3.0, 4.0],
            }
        )
        result = fit_expected_investment(
            frame,
            outcome="investment",
            predictors=("x",),
            group_cols=("industry", "fiscal_year"),
            min_obs=4,
        )
        self.assertTrue(result.panel["ie_residual"].isna().all())
        self.assertEqual(result.diagnostics.loc[0, "status"], "small_cell")
        self.assertTrue(result.panel["ie_model_outcome"].notna().all())

    def test_insufficient_residual_degrees_of_freedom_is_skipped(self) -> None:
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "x": [0.0, 1.0, 2.0, 3.0],
                "z": [0.0, 1.0, 4.0, 9.0],
                "investment": [1.0, 2.0, 3.0, 5.0],
            }
        )
        result = fit_expected_investment(
            frame,
            outcome="investment",
            predictors=("x", "z"),
            group_cols=("industry", "fiscal_year"),
            min_obs=2,
            min_residual_df=2,
        )
        self.assertEqual(
            result.diagnostics.loc[0, "status"], "insufficient_residual_df"
        )
        self.assertEqual(result.diagnostics.loc[0, "residual_df"], 1)
        self.assertTrue(result.panel["ie_residual"].isna().all())

    def test_rank_deficient_cell_is_estimated_and_flagged(self) -> None:
        x = np.linspace(-1, 1, 20)
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "x": x,
                "twice_x": 2 * x,
                "investment": 1 + x,
            }
        )
        result = fit_expected_investment(
            frame,
            outcome="investment",
            predictors=("x", "twice_x"),
            group_cols=("industry", "fiscal_year"),
        )
        self.assertTrue(result.diagnostics.loc[0, "rank_deficient"])
        self.assertEqual(result.diagnostics.loc[0, "status"], "estimated")

    def test_missing_group_key_is_excluded_and_audited(self) -> None:
        x = np.linspace(0, 1, 21)
        frame = pd.DataFrame(
            {
                "industry": ["A"] * 20 + [None],
                "fiscal_year": 2020,
                "x": x,
                "investment": 1 + x,
            }
        )
        result = fit_expected_investment(
            frame,
            outcome="investment",
            predictors=("x",),
            group_cols=("industry", "fiscal_year"),
        )
        self.assertTrue(np.isnan(result.panel.loc[20, "ie_residual"]))
        self.assertTrue(result.panel.loc[20, "ie_missing_model_group"])
        missing = result.diagnostics.query("status == 'missing_group_key'")
        self.assertEqual(missing.iloc[0]["n"], 1)

    def test_duplicate_dataframe_index_is_rejected(self) -> None:
        frame = pd.DataFrame(
            {"x": [1.0, 2.0], "investment": [2.0, 3.0]}, index=[0, 0]
        )
        with self.assertRaisesRegex(ValueError, "unique DataFrame index"):
            fit_expected_investment(
                frame,
                outcome="investment",
                predictors=("x",),
                min_obs=2,
            )

    def test_residual_metrics_keep_sign_and_magnitude_distinct(self) -> None:
        frame = pd.DataFrame(
            {"fiscal_year": [2020] * 5, "resid": [-2.0, -1.0, 0.0, 1.0, 2.0]}
        )
        result = add_residual_metrics(frame, residual_col="resid")
        self.assertEqual(result.loc[0, "ie_underinvestment"], 2.0)
        self.assertEqual(result.loc[4, "ie_overinvestment"], 2.0)
        self.assertEqual(result.loc[0, "ie_efficiency"], -2.0)
        self.assertEqual(result.loc[2, "ie_residual_group"], "benchmark")

    def test_residual_quartiles_are_balanced_for_distinct_values(self) -> None:
        frame = pd.DataFrame(
            {"fiscal_year": [2020] * 8, "resid": np.arange(-4.0, 4.0)}
        )
        result = add_residual_metrics(frame, residual_col="resid")
        counts = result["ie_residual_group"].value_counts()
        self.assertEqual(counts["under"], 2)
        self.assertEqual(counts["over"], 2)
        self.assertEqual(counts["benchmark"], 4)

    def test_missing_classification_key_does_not_create_benchmark_label(self) -> None:
        frame = pd.DataFrame(
            {"fiscal_year": [2020, np.nan], "resid": [1.0, 2.0]}
        )
        result = add_residual_metrics(frame, residual_col="resid")
        self.assertTrue(pd.isna(result.loc[1, "ie_residual_group"]))
        self.assertTrue(np.isnan(result.loc[1, "ie_efficient_below_median"]))

    def test_bhv_wrapper_uses_lagged_sales_growth(self) -> None:
        growth = np.linspace(-0.2, 0.2, 20)
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "ie_sales_growth_lag": growth,
                "ie_inv_bhv_total": 0.1 + 0.4 * growth,
            }
        )
        result = estimate_bhv_2009(frame)
        self.assertEqual(result.specification, "bhv2009")
        self.assertLess(result.panel["ie_residual"].abs().max(), 1e-12)

    def test_enomoto_wrapper_uses_japanese_ppe_investment(self) -> None:
        growth = np.linspace(-0.2, 0.3, 24)
        frame = pd.DataFrame(
            {
                "industry": "manufacturing",
                "fiscal_year": 2020,
                "ie_sales_growth_lag": growth,
                "ie_inv_enomoto_ppe": 0.05 + 0.4 * growth,
            }
        )
        result = estimate_enomoto_2024(frame)
        self.assertEqual(result.specification, "enomoto2024")
        self.assertLess(result.panel["ie_residual"].abs().max(), 1e-12)

    def test_chen_model_recovers_asymmetric_sales_slope(self) -> None:
        growth = np.linspace(-0.5, 0.5, 40)
        negative = (growth < 0).astype(float)
        investment = 0.1 + 0.2 * growth + 0.4 * negative * growth + 0.05 * negative
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "ie_sales_growth_lag": growth,
                "ie_inv_bhv_total": investment,
            }
        )
        result = estimate_chen_2011(frame)
        self.assertLess(result.panel["ie_residual"].abs().max(), 1e-12)

    def test_mcnichols_basic_returns_rank_space_residuals(self) -> None:
        q = np.linspace(0.5, 3.0, 24)
        cash_flow = np.linspace(-0.1, 0.3, 24)
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "ie_tobin_q_ms_lag": q,
                "ie_cash_flow_ms_net_capital": cash_flow,
                "ie_inv_ms_capex": 0.2 * q + 0.1 * cash_flow,
            }
        )
        result = estimate_mcnichols_stubben_2008(frame)
        self.assertEqual(result.specification, "mcnichols_stubben2008_basic")
        self.assertTrue(result.panel["ie_residual"].notna().all())
        self.assertTrue(np.isfinite(result.panel["ie_expected"]).all())
        np.testing.assert_allclose(
            result.panel["ie_ms_outcome_rank"],
            result.panel["ie_model_outcome"],
        )
        np.testing.assert_allclose(
            result.panel["ie_ms_outcome_rank"],
            result.panel["ie_expected"] + result.panel["ie_residual"],
        )

    def test_mcnichols_augmented_includes_quartile_intercepts_and_log_growth(self) -> None:
        n = 40
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "ie_tobin_q_ms_lag": np.linspace(0.5, 4.0, n),
                "ie_cash_flow_ms_net_capital": np.linspace(-0.2, 0.4, n),
                "ie_asset_growth_log_lag": np.linspace(-0.1, 0.2, n) ** 2,
                "ie_inv_ms_capex_lag": np.cos(np.linspace(0, 2, n)),
                "ie_inv_ms_capex": np.sin(np.linspace(0, 2, n)),
            }
        )
        result = estimate_mcnichols_stubben_2008(
            frame, augmented=True, min_obs=20
        )
        terms = set(result.coefficients["term"])
        self.assertTrue({"ie_q_q2", "ie_q_q3", "ie_q_q4"}.issubset(terms))
        self.assertIn("ie_asset_growth_log_lag", terms)

    def test_mcnichols_ranks_complete_cases_before_q_interactions(self) -> None:
        rng = np.random.default_rng(12)
        n = 41
        frame = pd.DataFrame(
            {
                "industry": "A",
                "fiscal_year": 2020,
                "ie_tobin_q_ms_lag": np.arange(n, dtype=float) + 0.5,
                "ie_cash_flow_ms_net_capital": rng.normal(size=n),
                "ie_asset_growth_log_lag": rng.normal(size=n),
                "ie_inv_ms_capex_lag": rng.normal(size=n),
                "ie_inv_ms_capex": rng.normal(size=n),
            }
        )
        frame.loc[n - 1, "ie_cash_flow_ms_net_capital"] = np.nan
        result = estimate_mcnichols_stubben_2008(
            frame, augmented=True, min_obs=20
        )
        self.assertEqual(result.panel.loc[0, "ie_ms_q_rank"], 0.0)
        self.assertEqual(result.panel.loc[n - 2, "ie_ms_q_rank"], 1.0)
        self.assertTrue(np.isnan(result.panel.loc[n - 1, "ie_ms_q_rank"]))
        for number in (2, 3, 4):
            indicator = result.panel[f"ie_q_q{number}"]
            self.assertTrue(set(indicator.dropna().unique()).issubset({0.0, 1.0}))
            np.testing.assert_allclose(
                result.panel[f"ie_q_x_q{number}"],
                result.panel["ie_ms_q_rank"] * indicator,
                equal_nan=True,
            )

    def test_biddle_hilary_cash_flow_coefficient_is_reported(self) -> None:
        n = 30
        cash_flow = np.linspace(-0.2, 0.4, n)
        q = np.sin(np.linspace(0, 3, n)) + 2
        firm = np.repeat(["F1", "F2"], n // 2)
        firm_intercept = np.where(firm == "F1", -0.3, 0.5)
        frame = pd.DataFrame(
            {
                "country": "US",
                "firm": firm,
                "fiscal_year": np.resize([2020, 2021, 2022], n),
                "ie_cash_flow_net_capital": cash_flow,
                "ie_tobin_q_lag": q,
                "ie_inv_bh_fixed_assets": firm_intercept + 0.7 * cash_flow + 0.2 * q,
            }
        )
        result = estimate_bh_2006_q_cash_flow(
            frame, transform_like_paper=False
        )
        coefficients = result.coefficients.set_index("term")
        self.assertAlmostEqual(
            coefficients.loc["ie_cash_flow_net_capital", "estimate"], 0.7
        )
        self.assertEqual(
            result.diagnostics.loc[0, "fixed_effect_method"], "absorbed"
        )
        self.assertFalse(
            result.coefficients["term"].str.startswith("firm_").any()
        )

    def test_biddle_hilary_excludes_singleton_firms(self) -> None:
        n = 21
        firm = np.array(["F1"] * 10 + ["F2"] * 10 + ["F3"])
        cash_flow = np.linspace(-0.2, 0.4, n)
        q = np.sin(np.linspace(0, 3, n)) + 2
        intercept = np.select(
            [firm == "F1", firm == "F2"], [-0.3, 0.5], default=1.0
        )
        frame = pd.DataFrame(
            {
                "country": "US",
                "firm": firm,
                "fiscal_year": np.resize([2020, 2021, 2022], n),
                "ie_cash_flow_net_capital": cash_flow,
                "ie_tobin_q_lag": q,
                "ie_inv_bh_fixed_assets": intercept + 0.7 * cash_flow + 0.2 * q,
            }
        )
        result = estimate_bh_2006_q_cash_flow(
            frame, transform_like_paper=False, min_obs=20
        )
        self.assertTrue(result.panel.loc[20, "ie_fixed_effect_singleton"])
        self.assertTrue(np.isnan(result.panel.loc[20, "ie_residual"]))
        self.assertEqual(result.diagnostics.loc[0, "singleton_fixed_effect_n"], 1)

    def test_richardson_full_predictor_set(self) -> None:
        n = 40
        x = np.linspace(0.1, 1.0, n)
        frame = pd.DataFrame(
            {
                "industry": np.where(np.arange(n) % 2, "A", "B"),
                "fiscal_year": np.where(np.arange(n) % 3, 2020, 2021),
                "ie_value_to_price_lag": x,
                "ie_leverage_capital_lag": x**2,
                "ie_cash_assets_lag": np.sin(x),
                "ie_firm_age_log_lag": np.log1p(np.arange(n)),
                "ie_size_log_assets_lag": 5 + x,
                "ie_stock_return_lag": np.cos(x),
                "ie_inv_richardson_new_lag": x**3,
            }
        )
        frame["ie_inv_richardson_new"] = (
            0.1
            - 0.2 * frame["ie_value_to_price_lag"]
            + 0.3 * frame["ie_cash_assets_lag"]
            + 0.05 * frame["ie_inv_richardson_new_lag"]
        )
        result = estimate_richardson_2006(frame)
        self.assertEqual(result.specification, "richardson2006")
        self.assertTrue(result.panel["ie_residual"].notna().all())
        self.assertLess(result.panel["ie_residual"].abs().max(), 1e-10)


if __name__ == "__main__":
    unittest.main()
