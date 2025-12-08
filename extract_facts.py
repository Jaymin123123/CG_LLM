import json
from typing import Dict, Any
from config import client, EXTRACTOR_MODEL
from schema import FACT_SCHEMA


EXTRACTION_SYSTEM_PROMPT = """
You are an expert remuneration analyst.

You will receive the full remuneration report text for a company.
Your task is to extract key remuneration facts into a STRICT JSON object that follows the given schema.

CRITICAL RULES (do not break these):
- DO NOT assume or infer values from external knowledge or general context. 
  Only use what is explicitly present in the provided text.
- If a value is not mentioned explicitly or cannot be derived directly from 
  numbers in the text, set it to null (or [] where appropriate).
- For "currency", only set a value if the text clearly specifies a currency 
  (e.g. "EUR", "euro(s)", "€", "GBP", "USD", "dollar(s)"). Otherwise set null.
- For percentage fields, parse the numeric part only (e.g. "150%" -> 150).
- You may compute simple differences or ratios if all input numbers are 
  explicitly given in the text (e.g. salary increase from 900,000 to 1,000,000).
- If you compute a value (such as a % increase), briefly describe how in extraction_notes.
- Be conservative: when in doubt, set the field to null and explain the doubt in extraction_notes.

Return ONLY valid JSON. No commentary, no markdown, no explanations outside JSON.
"""



def build_extraction_user_prompt(report_text: str, schema: Dict[str, Any]) -> str:
    return f"""
<REMUNERATION_REPORT>
{report_text}
</REMUNERATION_REPORT>

Using ONLY this text, fill the JSON schema below.
For every non-null numeric field, also populate the corresponding *_source field
with a short exact quote (or near-exact) from the report that justifies the value.

<SCHEMA>
{json.dumps(schema, indent=2)}
</SCHEMA>

Return ONLY valid JSON.
"""


def extract_facts_from_report(report_text: str) -> Dict[str, Any]:
    """
    Calls the LLM once to extract structured facts from the full Remuneration section.
    """

    response = client.chat.completions.create(
        model=EXTRACTOR_MODEL,
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_extraction_user_prompt(report_text, FACT_SCHEMA)
            }
        ],
        temperature=1,
    )

    content = response.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: try to salvage JSON-ish content
        raise ValueError(f"Model returned invalid JSON: {content[:500]}")

    return data

def compute_ceo_salary_increase_pct(facts):
    hist = facts.get("ceo_salary_history", [])
    by_year = {row["year"]: row["amount"] for row in hist if "year" in row and "amount" in row}
    if 2024 in by_year and 2023 in by_year:
        old, new = by_year[2023], by_year[2024]
        if old:
            return (new - old) / old * 100.0
    return None


if __name__ == "__main__":
    # Example usage: python extract_facts.py remuneration_report.txt facts.json
    import sys
    report_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(report_path, "r", encoding="utf-8") as f:
        report_text = f.read()

    facts = extract_facts_from_report(report_text)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2)

    print(f"Saved extracted facts to {output_path}")
