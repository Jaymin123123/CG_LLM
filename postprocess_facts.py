# postprocess_facts.py

from typing import Dict, Any, List, Optional


def _compute_salary_increase_pct_from_history(
    salary_history: List[Dict[str, Any]]
) -> Optional[float]:
    """
    Compute 1-year CEO salary increase (latest year vs previous year)
    from a list of salary records like:
      { "year": 2023, "amount": 1000000, "currency": "EUR", "source": "..." }

    Returns a percentage (e.g. 5.0 for +5%) or None if not enough data.
    """
    if not isinstance(salary_history, list) or len(salary_history) < 2:
        return None

    # Keep only records with year and amount
    clean = []
    for row in salary_history:
        try:
            year = int(row.get("year"))
            amount = float(row.get("amount"))
            clean.append({"year": year, "amount": amount})
        except (TypeError, ValueError):
            continue

    if len(clean) < 2:
        return None

    # Sort by year ascending
    clean.sort(key=lambda x: x["year"])
    latest = clean[-1]
    previous = clean[-2]

    old = previous["amount"]
    new = latest["amount"]
    if old <= 0:
        return None

    return (new - old) / old * 100.0


def _compute_total_esg_weight(metrics: List[Dict[str, Any]]) -> Optional[float]:
    """
    Sum weight_pct for metrics where category == "esg".

    Returns total ESG weight or None if no usable ESG metrics or weights.
    """
    if not isinstance(metrics, list):
        return None

    total = 0.0
    count = 0
    for m in metrics:
        if not isinstance(m, dict):
            continue
        if m.get("category") != "esg":
            continue
        weight = m.get("weight_pct")
        if weight is None:
            continue
        try:
            w = float(weight)
        except (TypeError, ValueError):
            continue
        total += w
        count += 1

    if count == 0:
        return None
    return total


def _has_any_esg_metric(sti_metrics: List[Dict[str, Any]],
                        ltip_metrics: List[Dict[str, Any]]) -> bool:
    """
    Return True if any metric in STI or LTIP has category == "esg".
    """
    for metrics in (sti_metrics, ltip_metrics):
        if not isinstance(metrics, list):
            continue
        for m in metrics:
            if isinstance(m, dict) and m.get("category") == "esg":
                return True
    return False


def postprocess_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Take a single facts JSON dict (as returned by the LLM extractor)
    and enrich it with deterministic derived values:

    - ceo_salary_increase_pct (if missing) from ceo_salary_history
    - sti_total_esg_weight_pct / ltip_total_esg_weight_pct from sti_metrics / ltip_metrics
    - esg_metrics_incentives_present if any ESG metrics exist

    Returns the same dict (mutated) for convenience.
    """
    # --- CEO salary increase from history ---
    if facts.get("ceo_salary_increase_pct") is None:
        salary_history = facts.get("ceo_salary_history", [])
        increase = _compute_salary_increase_pct_from_history(salary_history)
        if increase is not None:
            facts["ceo_salary_increase_pct"] = increase
            # Optional: you can add / update a source explanation
            notes = facts.get("ceo_salary_increase_pct_source")
            if not notes:
                facts["ceo_salary_increase_pct_source"] = (
                    "Computed from ceo_salary_history as latest vs previous year."
                )

    # --- ESG total weights for STI and LTIP ---
    sti_metrics = facts.get("sti_metrics", [])
    ltip_metrics = facts.get("ltip_metrics", [])

    if facts.get("sti_total_esg_weight_pct") is None:
        sti_esg_weight = _compute_total_esg_weight(sti_metrics)
        if sti_esg_weight is not None:
            facts["sti_total_esg_weight_pct"] = sti_esg_weight

    if facts.get("ltip_total_esg_weight_pct") is None:
        ltip_esg_weight = _compute_total_esg_weight(ltip_metrics)
        if ltip_esg_weight is not None:
            facts["ltip_total_esg_weight_pct"] = ltip_esg_weight

    # --- Simple esg_metrics_incentives_present flag ---
    if facts.get("esg_metrics_incentives_present") is None:
        facts["esg_metrics_incentives_present"] = _has_any_esg_metric(
            sti_metrics, ltip_metrics
        )

    return facts
