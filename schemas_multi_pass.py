# schemas_multi_pass.py
# Multi-pass schemas for whole-annual-report extraction (format-agnostic)

FACT_SCHEMA_BASE = {
    "company_name": None,
    "financial_year": None,
    "currency": None,

    "total_dilution_pct": None,
    "total_dilution_pct_source": None,

    "ltip_dilution_pct": None,
    "ltip_dilution_pct_source": None,

    "stip_dilution_pct": None,
    "stip_dilution_pct_source": None,

    "dilution_policy_limit_pct": None,
    "dilution_policy_limit_pct_source": None,

    "ceo_salary_increase_pct": None,
    "ceo_salary_increase_pct_source": None,

    "workforce_salary_increase_pct": None,
    "workforce_salary_increase_pct_source": None,

    "ceo_target_bonus_pct_of_salary": None,
    "ceo_target_bonus_pct_of_salary_source": None,

    "ceo_max_bonus_pct_of_salary": None,
    "ceo_max_bonus_pct_of_salary_source": None,

    "ceo_ltip_max_pct_of_salary": None,
    "ceo_ltip_max_pct_of_salary_source": None,

    "clawback_provision": None,
    "clawback_provision_source": None,

    "malus_provision": None,
    "malus_provision_source": None,

    "post_cessation_holding_years": None,
    "post_cessation_holding_years_source": None,

    "shareholding_requirement_ceo": None,
    "shareholding_requirement_ceo_source": None,

    "esg_metrics_incentives_present": None,
    "esg_metrics_incentives_present_source": None,

    "performance_metrics": [],
    "performance_metrics_source": None,

    "key_concerns": [],
    "key_concerns_source": None,

    "extraction_notes": "",
    "source_pdf": None,

    # optional, but matches your example
    "rem_pages_start": None,
    "rem_pages_end": None,

    "financial_performance": {
        "eps_current": None,
        "eps_current_source": None,
        "eps_prior": None,
        "eps_prior_source": None,
        "eps_change_pct": None,

        "profit_attributable_current_k": None,
        "profit_attributable_current_k_source": None,
        "profit_attributable_prior_k": None,
        "profit_attributable_prior_k_source": None,
        "profit_attributable_change_pct": None,

        "financial_source_pages_hint": [],
        "financial_sources": {
            "eps_source_snippet": None,
            "profit_source_snippet": None,
        },
    },
}

# PASS 1: Global metadata (company name, year, currency) + Rem page hints (optional)
SCHEMA_META = {
    "company_name": None,
    "financial_year": None,
    "currency": None,
    "source_pdf": None,
    "rem_pages_start": None,
    "rem_pages_end": None,

    "company_name_source": None,
    "financial_year_source": None,
    "currency_source": None,
    "rem_pages_source": None,

    "extraction_notes": "",
}

# PASS 2: Dilution & share schemes (may live in notes/share capital/LTIP plan)
SCHEMA_DILUTION = {
    "total_dilution_pct": None,
    "total_dilution_pct_source": None,

    "ltip_dilution_pct": None,
    "ltip_dilution_pct_source": None,

    "stip_dilution_pct": None,
    "stip_dilution_pct_source": None,

    "dilution_policy_limit_pct": None,
    "dilution_policy_limit_pct_source": None,

    "extraction_notes": "",
}

# PASS 3: Pay structure & opportunity (salary/bonus/LTIP opportunity, holding, shareholding)
SCHEMA_PAY_STRUCTURE = {
    "ceo_salary_increase_pct": None,
    "ceo_salary_increase_pct_source": None,

    "workforce_salary_increase_pct": None,
    "workforce_salary_increase_pct_source": None,

    "ceo_target_bonus_pct_of_salary": None,
    "ceo_target_bonus_pct_of_salary_source": None,

    "ceo_max_bonus_pct_of_salary": None,
    "ceo_max_bonus_pct_of_salary_source": None,

    "ceo_ltip_max_pct_of_salary": None,
    "ceo_ltip_max_pct_of_salary_source": None,

    "post_cessation_holding_years": None,
    "post_cessation_holding_years_source": None,

    "shareholding_requirement_ceo": None,
    "shareholding_requirement_ceo_source": None,

    "extraction_notes": "",
}

# PASS 4: Governance features (malus/clawback) + ESG + metrics + concerns
SCHEMA_GOV_ESG = {
    "clawback_provision": None,
    "clawback_provision_source": None,

    "malus_provision": None,
    "malus_provision_source": None,

    "esg_metrics_incentives_present": None,
    "esg_metrics_incentives_present_source": None,

    "performance_metrics": [],
    "performance_metrics_source": None,

    "key_concerns": [],
    "key_concerns_source": None,

    "extraction_notes": "",
}

# PASS 5: Financial performance (EPS/profit) – must return both years with evidence
SCHEMA_FINANCIALS = {
    "financial_performance": {
        "eps_current": None,
        "eps_current_source": None,
        "eps_prior": None,
        "eps_prior_source": None,

        "profit_attributable_current_k": None,
        "profit_attributable_current_k_source": None,
        "profit_attributable_prior_k": None,
        "profit_attributable_prior_k_source": None,

        "financial_source_pages_hint": [],
        "financial_sources": {
            "eps_source_snippet": None,
            "profit_source_snippet": None,
        },
    },
    "extraction_notes": "",
}

MULTI_PASS = [
    ("meta", SCHEMA_META),
    ("dilution", SCHEMA_DILUTION),
    ("pay_structure", SCHEMA_PAY_STRUCTURE),
    ("gov_esg", SCHEMA_GOV_ESG),
    ("financials", SCHEMA_FINANCIALS),
]
