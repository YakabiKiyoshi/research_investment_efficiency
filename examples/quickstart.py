"""Small executable example using a synthetic industry-year panel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from investment_efficiency import estimate_bhv_2009


rng = np.random.default_rng(7)
panel = pd.DataFrame(
    {
        "firm": [f"F{number:02d}" for number in range(24)],
        "fiscal_year": 2025,
        "industry": "manufacturing",
        "ie_sales_growth_lag": np.linspace(-0.2, 0.3, 24),
    }
)
panel["ie_inv_bhv_total"] = (
    0.08 + 0.35 * panel["ie_sales_growth_lag"] + rng.normal(0, 0.01, len(panel))
)

result = estimate_bhv_2009(panel)
print(result.panel[["firm", "ie_residual", "ie_residual_group"]].head())
print(result.diagnostics)
