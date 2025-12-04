FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "financial_year": {"type": "string"},
        "currency": {"type": "string"},

        # Key dilution & share limits
        "total_dilution_pct": {"type": "number"},
        "ltip_dilution_pct": {"type": "number"},
        "stip_dilution_pct": {"type": "number"},
        "dilution_policy_limit_pct": {"type": "number"},

        # Pay increases & structure
        "ceo_salary_increase_pct": {"type": "number"},
        "workforce_salary_increase_pct": {"type": "number"},
        "ceo_target_bonus_pct_of_salary": {"type": "number"},
        "ceo_max_bonus_pct_of_salary": {"type": "number"},
        "ceo_ltip_max_pct_of_salary": {"type": "number"},

        # Governance features
        "clawback_provision": {"type": "boolean"},
        "malus_provision": {"type": "boolean"},
        "post_cessation_holding_years": {"type": "number"},
        "shareholding_requirement_ceo": {"type": "number"},  # x times salary

        # ESG & metrics
        "esg_metrics_incentives_present": {"type": "boolean"},
        "performance_metrics": {
            "type": "array",
            "items": {"type": "string"}
        },

        # Flags / concerns (model can populate)
        "key_concerns": {
            "type": "array",
            "items": {"type": "string"}
        },

        # For traceability
        "extraction_notes": {"type": "string"}
    },
    "required": [
        "company_name",
        "financial_year",
        "currency"
    ],
    "additionalProperties": True
}
