"""Machine-readable literature-to-implementation registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Specification:
    """Metadata for one implemented empirical measure or design."""

    id: str
    citation: str
    journal: str
    year: int
    doi: str
    geography: str
    family: str
    implementation: str
    primary_output: str
    caution: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SPECIFICATIONS: tuple[Specification, ...] = (
    Specification(
        id="bh2006_q_cashflow",
        citation="Biddle and Hilary (2006)",
        journal="The Accounting Review",
        year=2006,
        doi="https://doi.org/10.2308/accr.2006.81.5.963",
        geography="US, Japan, and international",
        family="investment-cash-flow sensitivity",
        implementation="add_capital_investment_inputs; estimate_bh_2006_q_cash_flow",
        primary_output="cash-flow coefficient in coefficients",
        caution="Uses arctangent/log transforms and firm fixed effects; sensitivity is a coefficient.",
    ),
    Specification(
        id="bh2006_cfsi",
        citation="Biddle and Hilary (2006)",
        journal="The Accounting Review",
        year=2006,
        doi="https://doi.org/10.2308/accr.2006.81.5.963",
        geography="US and Japan",
        family="rolling cash-flow sensitivity",
        implementation="cash_flow_sensitivity_index",
        primary_output="rolling CFSI",
        caution="Negative cash flows are set to zero; ten complete years are the default.",
    ),
    Specification(
        id="richardson2006",
        citation="Richardson (2006)",
        journal="Review of Accounting Studies",
        year=2006,
        doi="https://doi.org/10.1007/s11142-006-9012-1",
        geography="US",
        family="expected new investment",
        implementation="estimate_richardson_2006",
        primary_output="ie_residual",
        caution="The original interpretation focuses on positive residual over-investment.",
    ),
    Specification(
        id="mcnichols_stubben2008_basic",
        citation="McNichols and Stubben (2008)",
        journal="The Accounting Review",
        year=2008,
        doi="https://doi.org/10.2308/accr.2008.83.6.1571",
        geography="US",
        family="ranked Q model",
        implementation="estimate_mcnichols_stubben_2008(augmented=False)",
        primary_output="ie_residual",
        caution="Residuals are in within-industry-year rank units.",
    ),
    Specification(
        id="mcnichols_stubben2008_augmented",
        citation="McNichols and Stubben (2008)",
        journal="The Accounting Review",
        year=2008,
        doi="https://doi.org/10.2308/accr.2008.83.6.1571",
        geography="US",
        family="ranked nonlinear Q model",
        implementation="estimate_mcnichols_stubben_2008(augmented=True)",
        primary_output="ie_residual",
        caution="Adds Q-quartile intercepts/slopes, lagged log asset growth, and lagged investment.",
    ),
    Specification(
        id="bhv2009",
        citation="Biddle, Hilary, and Verdi (2009)",
        journal="Journal of Accounting and Economics",
        year=2009,
        doi="https://doi.org/10.1016/j.jacceco.2009.09.001",
        geography="US",
        family="sales-growth residual",
        implementation="estimate_bhv_2009",
        primary_output="ie_residual and ie_residual_group",
        caution="Industry-year cells require at least 20 complete observations.",
    ),
    Specification(
        id="chen2011",
        citation="Chen, Hope, Li, and Wang (2011)",
        journal="The Accounting Review",
        year=2011,
        doi="https://doi.org/10.2308/accr-10040",
        geography="Emerging-market private firms",
        family="asymmetric sales-growth residual",
        implementation="estimate_chen_2011",
        primary_output="ie_residual",
        caution="Separates the investment slope when prior sales growth is negative.",
    ),
    Specification(
        id="jlw2014",
        citation="Jung, Lee, and Weber (2014)",
        journal="Contemporary Accounting Research",
        year=2014,
        doi="https://doi.org/10.1111/1911-3846.12053",
        geography="US",
        family="labor investment efficiency",
        implementation="add_labor_investment_inputs; estimate_jlw_2014",
        primary_output="ie_labor_absolute_abnormal_net_hiring",
        caution="Employee headcount measures labor quantity, not skill or wage investment.",
    ),
    Specification(
        id="enomoto2024",
        citation="Enomoto, Rhee, Jung, and Shuto (2024)",
        journal="Japan and the World Economy",
        year=2024,
        doi="https://doi.org/10.1016/j.japwor.2024.101280",
        geography="Japan",
        family="conditional over/under-investment",
        implementation="estimate_enomoto_2024; add_overinvestment_likelihood",
        primary_output="ie_residual, ie_residual_group, and ie_overinvestment_likelihood",
        caution="OverI is an ex-ante liquidity score, not realized abnormal investment.",
    ),
    Specification(
        id="shimizu2025",
        citation="Shimizu (2025)",
        journal="Accounting Progress",
        year=2025,
        doi="https://doi.org/10.34605/jaa.2025.26_57",
        geography="Japan",
        family="labor investment efficiency",
        implementation="add_labor_investment_inputs; estimate_jlw_2014",
        primary_output="ie_labor_absolute_abnormal_net_hiring",
        caution="Japanese replication family; source-specific item mapping remains explicit.",
    ),
)


def list_specifications() -> list[dict[str, object]]:
    """Return registry rows suitable for a DataFrame or JSON."""

    return [specification.to_dict() for specification in SPECIFICATIONS]


def get_specification(specification_id: str) -> Specification:
    """Return one registry entry by stable identifier."""

    for specification in SPECIFICATIONS:
        if specification.id == specification_id:
            return specification
    available = ", ".join(item.id for item in SPECIFICATIONS)
    raise KeyError(f"unknown specification {specification_id!r}; available: {available}")
