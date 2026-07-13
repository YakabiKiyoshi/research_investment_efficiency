from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from investment_efficiency.panel import panel_lag, validate_panel, winsorize


class PanelTests(unittest.TestCase):
    def test_duplicate_firm_year_is_rejected(self) -> None:
        frame = pd.DataFrame({"firm": [1, 1], "year": [2020, 2020], "x": [1, 2]})
        with self.assertRaisesRegex(ValueError, "must be unique"):
            validate_panel(frame, firm_col="firm", period_col="year")

    def test_duplicate_dataframe_index_is_rejected(self) -> None:
        frame = pd.DataFrame(
            {"firm": [1, 2], "year": [2020, 2020], "x": [1, 2]},
            index=[7, 7],
        )
        with self.assertRaisesRegex(ValueError, "unique DataFrame index"):
            validate_panel(frame, firm_col="firm", period_col="year")

    def test_consecutive_lag_does_not_cross_gap(self) -> None:
        frame = pd.DataFrame(
            {"firm": [1, 1, 1], "year": [2020, 2022, 2023], "x": [10, 20, 30]}
        )
        lagged = panel_lag(
            frame, "x", firm_col="firm", period_col="year", require_consecutive=True
        )
        self.assertTrue(np.isnan(lagged.iloc[0]))
        self.assertTrue(np.isnan(lagged.iloc[1]))
        self.assertEqual(lagged.iloc[2], 20)

    def test_winsorization_can_be_year_specific(self) -> None:
        frame = pd.DataFrame(
            {"year": [1, 1, 1, 2, 2, 2], "x": [0, 1, 100, 10, 11, 1000]}
        )
        result = winsorize(frame, ["x"], by=["year"], lower=0.0, upper=0.5)
        self.assertEqual(result.loc[2, "x"], 1)
        self.assertEqual(result.loc[5, "x"], 11)


if __name__ == "__main__":
    unittest.main()
