# extract_financials_llm.py
import json
from typing import Dict, Any, List
from config import client, EXTRACT_MODEL  # e.g., gpt-4o / gpt-4.1-mini etc.

FIN_SYSTEM = """
You extract financial performance facts from annual reports.

Return STRICT JSON only. No markdown.

Rules:
- Use only the provided text.
- If a value is not explicitly present, return null.
- Prefer Basic EPS (or Basic and diluted EPS if only one is given).
- Profit attributable should be profit attributable to owners/ shareholders/ equity holders (if stated).
- Always include evidence with page number and a short quote/snippet (max ~200 chars).
"""

def extract_financial_performance_llm(pages_with_numbers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    pages_with_numbers: [{"page": 213, "text": "..."} , ...]
    """
    user = {
        "pages": pages_with_numbers,
        "schema": {
            "eps_current": "number|null",
            "eps_prior": "number|null",
            "profit_attributable_current_k": "number|null",
            "profit_attributable_prior_k": "number|null",
            "evidence": [
                {"metric": "string", "page": "int", "quote": "string"}
            ]
        }
    }

    resp = client.chat.completions.create(
        model=EXTRACT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": FIN_SYSTEM},
            {"role": "user", "content": json.dumps(user)}
        ],
        temperature=0.0
    )
    return json.loads(resp.choices[0].message.content)
