"""Command-line interface for canonical-schema panels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from .measures import CapitalColumns, add_capital_investment_inputs
from .models import (
    ExpectedInvestmentResult,
    estimate_bh_2006_q_cash_flow,
    estimate_bhv_2009,
    estimate_chen_2011,
    estimate_enomoto_2024,
    estimate_mcnichols_stubben_2008,
    estimate_richardson_2006,
)
from .specifications import list_specifications


_FIT_SPEC_ALIASES = {
    "bh2006": "bh2006_q_cashflow",
    "mcnichols2008-basic": "mcnichols_stubben2008_basic",
    "mcnichols2008-augmented": "mcnichols_stubben2008_augmented",
}
_FIT_SPEC_IDS = (
    "bh2006_q_cashflow",
    "bhv2009",
    "chen2011",
    "enomoto2024",
    "richardson2006",
    "mcnichols_stubben2008_basic",
    "mcnichols_stubben2008_augmented",
)
_FIT_SPEC_CHOICES = tuple(sorted((*_FIT_SPEC_IDS, *_FIT_SPEC_ALIASES)))


def _read(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path, encoding="utf-8-sig")
    raise ValueError("input must be CSV or Parquet")


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        frame.to_parquet(path, index=False)
    elif suffix in {".csv", ".txt"}:
        frame.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        raise ValueError("output must be CSV or Parquet")


def _write_audit(result: ExpectedInvestmentResult, output: Path) -> None:
    stem = output.with_suffix("")
    _write(result.panel, output)
    result.coefficients.to_csv(
        Path(f"{stem}.coefficients.csv"), index=False, encoding="utf-8-sig"
    )
    result.diagnostics.to_csv(
        Path(f"{stem}.diagnostics.csv"), index=False, encoding="utf-8-sig"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="investment-efficiency",
        description="Construct literature-based investment-efficiency measures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = subparsers.add_parser("specs", help="list implemented specifications")
    specs.add_argument("--json", action="store_true", dest="as_json")

    prepare = subparsers.add_parser(
        "prepare", help="construct capital inputs using canonical column names"
    )
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument(
        "--missing-components", choices=("zero", "propagate"), default="zero"
    )
    prepare.add_argument(
        "--missing-dividends", choices=("zero", "propagate"), default="zero"
    )
    prepare.add_argument("--allow-year-gaps", action="store_true")

    fit = subparsers.add_parser("fit", help="fit a canonical expected-investment model")
    fit.add_argument("--input", type=Path, required=True)
    fit.add_argument("--output", type=Path, required=True)
    fit.add_argument(
        "--spec",
        choices=_FIT_SPEC_CHOICES,
        required=True,
    )
    fit.add_argument("--min-obs", type=int, default=20)
    fit.add_argument("--min-residual-df", type=int, default=1)
    fit.add_argument(
        "--country-col",
        default="country",
        help="country grouping column required by bh2006_q_cashflow (default: country)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    args = _parser().parse_args(argv)
    if args.command == "specs":
        rows = list_specifications()
        if args.as_json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(pd.DataFrame(rows)[["id", "citation", "journal", "family"]].to_string(index=False))
        return 0

    if args.command == "prepare":
        prepared = add_capital_investment_inputs(
            _read(args.input),
            columns=CapitalColumns(),
            missing_components=args.missing_components,
            missing_dividends=args.missing_dividends,
            require_consecutive=not args.allow_year_gaps,
        )
        _write(prepared, args.output)
        return 0

    panel = _read(args.input)
    specification = _FIT_SPEC_ALIASES.get(args.spec, args.spec)
    common = {
        "min_obs": args.min_obs,
        "min_residual_df": args.min_residual_df,
    }
    if specification == "bh2006_q_cashflow":
        result = estimate_bh_2006_q_cash_flow(
            panel, group_cols=(args.country_col,), **common
        )
    elif specification == "bhv2009":
        result = estimate_bhv_2009(panel, **common)
    elif specification == "chen2011":
        result = estimate_chen_2011(panel, **common)
    elif specification == "enomoto2024":
        result = estimate_enomoto_2024(panel, **common)
    elif specification == "richardson2006":
        result = estimate_richardson_2006(panel, **common)
    elif specification in {
        "mcnichols_stubben2008_basic",
        "mcnichols_stubben2008_augmented",
    }:
        result = estimate_mcnichols_stubben_2008(
            panel,
            augmented=specification.endswith("augmented"),
            **common,
        )
    else:  # pragma: no cover - argparse choices and aliases make this unreachable
        raise ValueError(f"unsupported fit specification: {specification}")
    _write_audit(result, args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
