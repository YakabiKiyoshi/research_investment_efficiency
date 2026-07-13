from __future__ import annotations

import io
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

from investment_efficiency.cli import main
from investment_efficiency.specifications import (
    get_specification,
    list_specifications,
)


class RegistryAndCliTests(unittest.TestCase):
    def test_registry_ids_are_unique_and_resolvable(self) -> None:
        rows = list_specifications()
        identifiers = [row["id"] for row in rows]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(get_specification("bhv2009").year, 2009)
        self.assertGreaterEqual(len(rows), 10)

    def test_specs_cli_can_emit_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(["specs", "--json"])
        self.assertEqual(status, 0)
        rows = json.loads(stdout.getvalue())
        self.assertTrue(any(row["id"] == "enomoto2024" for row in rows))

    def test_fit_cli_writes_panel_and_audit_files(self) -> None:
        n = 30
        frame = pd.DataFrame(
            {
                "country": "US",
                "firm": np.repeat(["F1", "F2"], n // 2),
                "fiscal_year": np.resize([2020, 2021, 2022], n),
                "ie_inv_bh_fixed_assets": np.linspace(0.05, 0.35, n),
                "ie_cash_flow_net_capital": np.linspace(-0.1, 0.3, n),
                "ie_tobin_q_lag": np.linspace(0.8, 2.5, n),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "prepared.csv")
            output = Path(directory, "measures.csv")
            frame.to_csv(source, index=False)
            status = main(
                [
                    "fit",
                    "--spec",
                    "bh2006",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            self.assertTrue(output.exists())
            self.assertTrue(Path(directory, "measures.coefficients.csv").exists())
            diagnostics = pd.read_csv(
                Path(directory, "measures.diagnostics.csv")
            )
            self.assertEqual(diagnostics.loc[0, "status"], "estimated")
            self.assertGreaterEqual(diagnostics.loc[0, "residual_df"], 1)

    def test_fit_cli_accepts_registry_id_and_custom_country_column(self) -> None:
        n = 30
        frame = pd.DataFrame(
            {
                "nation": "US",
                "firm": np.repeat(["F1", "F2"], n // 2),
                "fiscal_year": np.resize([2020, 2021, 2022], n),
                "ie_inv_bh_fixed_assets": np.linspace(0.05, 0.35, n),
                "ie_cash_flow_net_capital": np.linspace(-0.1, 0.3, n),
                "ie_tobin_q_lag": np.linspace(0.8, 2.5, n),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "prepared.csv")
            output = Path(directory, "measures.csv")
            frame.to_csv(source, index=False)
            status = main(
                [
                    "fit",
                    "--spec",
                    "bh2006_q_cashflow",
                    "--country-col",
                    "nation",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            self.assertTrue(output.exists())

    def test_prepare_cli_can_explicitly_allow_year_gaps(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": ["A", "A"],
                "fiscal_year": [2020, 2022],
                "assets": [100.0, 120.0],
                "sales": [80.0, 100.0],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "raw.csv")
            output = Path(directory, "prepared.csv")
            frame.to_csv(source, index=False)
            status = main(
                [
                    "prepare",
                    "--allow-year-gaps",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            prepared = pd.read_csv(output)
            self.assertAlmostEqual(prepared.loc[1, "ie_sales_growth"], 0.25)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "pyarrow not installed")
    def test_prepare_cli_round_trips_parquet(self) -> None:
        frame = pd.DataFrame(
            {
                "firm": ["A", "A"],
                "fiscal_year": [2020, 2021],
                "assets": [100.0, 120.0],
                "sales": [80.0, 100.0],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "raw.parquet")
            output = Path(directory, "prepared.parquet")
            frame.to_parquet(source, index=False)
            status = main(
                [
                    "prepare",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            prepared = pd.read_parquet(output)
            self.assertAlmostEqual(prepared.loc[1, "ie_sales_growth"], 0.25)


if __name__ == "__main__":
    unittest.main()
