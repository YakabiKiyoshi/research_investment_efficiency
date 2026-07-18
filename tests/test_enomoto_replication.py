import importlib.util
from pathlib import Path

import pandas as pd


P = Path(__file__).parents[1] / "scripts" / "analysis" / "run_enomoto_2024.py"
spec = importlib.util.spec_from_file_location("enomoto", P)
enomoto = importlib.util.module_from_spec(spec); spec.loader.exec_module(enomoto)


def test_load_is_consolidated_and_twelve_month(tmp_path):
    rows=[]
    for scope, months in [(2,12),(1,12),(2,6)]:
        row={c: 1 for c in enomoto.RAW}; row.update(FIRM="x", NKCODE=scope*100+months,
            FiscalEnd="2005-03-31", Listing=1, MACC=months, Industry="m", CodeIndustry=10,
            A01_SCFLG=scope, A01_SECFLG=1, SourceMissingAssets=False, SourceMissingPPEAny=False)
        rows.append(row)
    p=tmp_path/"x.csv"; pd.DataFrame(rows).to_csv(p,index=False)
    x,_=enomoto.load_panel(p,2013)
    assert len(x)==1 and x.iloc[0].statementScope=="consolidated" and x.iloc[0].months==12


def test_basis_switch_breaks_lag():
    x=pd.DataFrame({"firm_id":[1,1],"fiscal_end":pd.to_datetime(["2000-03-31","2001-03-31"]),
      "accountingBasis":["JGAAP_consolidated","IFRS"], **{c:[10.,11.] for c in ["assets","current_assets","cash","trading_securities","short_loans_receivable","current_liabilities","short_debt","long_debt","ppe","sales","cfo_reported","depreciation","ni_total","ni_parent","ni_nci","extra_gain","extra_loss","book_equity","market_equity"]}})
    z=enomoto.add_measurements(x)
    assert not bool(z.iloc[1].lag_ok) and pd.isna(z.iloc[1].lag_assets)


def test_aq_is_negative_sd_of_prior_five_and_excludes_current():
    residual = pd.Series([1., 2., 3., 4., 5., 100.])
    aq = enomoto.negative_prior_five_sd(
        residual, pd.Series([1] * 6), pd.Series([True, False, False, False, False, False]))
    assert aq.iloc[:5].isna().all()
    assert aq.iloc[5] == -residual.iloc[:5].std()


def test_main_lane_does_not_turn_missing_raw_item_into_zero():
    fields = ["assets", "current_assets", "cash", "trading_securities",
              "short_loans_receivable", "current_liabilities", "short_debt", "long_debt",
              "ppe", "sales", "cfo_reported", "depreciation", "ni_total", "ni_parent",
              "ni_nci", "extra_gain", "extra_loss", "book_equity", "market_equity"]
    x = pd.DataFrame({"firm_id": [1, 1],
        "fiscal_end": pd.to_datetime(["2000-03-31", "2001-03-31"]),
        "accountingBasis": ["JGAAP", "JGAAP"], **{c: [10., 11.] for c in fields}})
    x.loc[1, "trading_securities"] = float("nan")
    strict = enomoto.add_measurements(x)
    proxy = enomoto.add_measurements(x, missing_as_zero_proxy=True)
    assert pd.isna(strict.loc[1, "tca"])
    assert pd.notna(proxy.loc[1, "tca"])
