# extract_facts_multi_pass.py
import json
import re
from copy import deepcopy
from typing import Dict, Any, List, Tuple
import os

from PyPDF2 import PdfReader

from config import client, EXTRACTOR_MODEL
from schemas_multi_pass import FACT_SCHEMA_BASE, MULTI_PASS


# ----------------------------
# PDF -> numbered text
# ----------------------------

def read_pdf_pages(pdf_path: str) -> List[str]:
    reader = PdfReader(pdf_path)
    pages: List[str] = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def pages_to_numbered_text(pages: List[str], start_page_num: int = 1) -> str:
    # Preserve page boundaries for evidence
    out = []
    for i, txt in enumerate(pages, start=start_page_num):
        t = (txt or "").strip()
        if not t:
            continue
        out.append(f"\n\n=== PAGE {i} ===\n{t}")
    return "".join(out)


# ----------------------------
# LLM extraction core
# ----------------------------

COMMON_RULES = """
CRITICAL RULES (must follow):
- Only use what is explicitly present in the provided report text.
- If a value is not explicitly stated, set it to null (or [] for lists).
- For any non-null field you output, you MUST provide a corresponding *_source field as:
  "PAGE <n>: <short quote>" copied from the report.
- If you cannot provide both a PAGE number and a quote for a value, set that value to null.
- For percentage fields, output the numeric value only (e.g., "150%" -> 150).
- Currency: set only if explicitly shown (EUR/€, GBP/£, USD/$, etc.). Otherwise null.
- Avoid inference. Be conservative.
"""

SYSTEM_PROMPTS = {
    "meta": f"""
You are an expert annual report analyst. Extract company metadata.
{COMMON_RULES}
Return ONLY valid JSON.
""",
    "dilution": f"""
You are an expert share plans / dilution analyst.
Search the entire annual report for LTIP/STIP dilution limits, share scheme headroom, dilution policy limits, and any explicit dilution % figures.
{COMMON_RULES}
Return ONLY valid JSON.
""",
    "pay_structure": f"""
You are an expert remuneration policy analyst.
Extract CEO pay opportunity levels (salary change, bonus target/max, LTIP opportunity), plus holding/shareholding requirements.
If salary increase % is not explicitly given but both prior and current salary numbers are present, you may compute it and cite both values in the source quote.
{COMMON_RULES}
Return ONLY valid JSON.
""",
    "gov_esg": f"""
You are an expert remuneration governance analyst.
Extract whether malus and clawback provisions exist, whether ESG metrics are present in incentives, plus list performance metrics and key concerns explicitly stated.
{COMMON_RULES}
Return ONLY valid JSON.
""",
    "financials": f"""
You are an expert financial reporting analyst.
Extract ONLY:
- EPS current year and prior year (must be numeric EPS values, not years),
- profit attributable (current/prior) if explicitly stated (as k = thousands, if units shown; otherwise leave null).

STRICT FINANCIAL RULES:
- eps_prior MUST be a numeric EPS value for the prior year (e.g., 0.18), NOT a year like 2023/2024.
- If the report only states EPS for one year, set the other year to null.
- If you see a year number near EPS, do not treat it as EPS.
- Provide PAGE+QUOTE evidence for eps_current and eps_prior if non-null.
- You may include a short eps_source_snippet and profit_source_snippet (with PAGE markers) inside financial_sources.

{COMMON_RULES}
Return ONLY valid JSON.
""",
}


def llm_extract(pass_name: str, schema: Dict[str, Any], numbered_report_text: str) -> Dict[str, Any]:
    system_prompt = SYSTEM_PROMPTS.get(pass_name, f"You are an expert analyst.\n{COMMON_RULES}\nReturn ONLY valid JSON.\n")

    user_prompt = f"""
You will be given an annual report with page markers like "=== PAGE 213 ===".
Extract ONLY the fields in the schema below.

Evidence requirement:
- For every non-null numeric/boolean/string field, provide the corresponding *_source field as:
  "PAGE <n>: <quote>"

If you cannot provide BOTH page and quote, output null for that field.

<ANNUAL_REPORT>
{numbered_report_text}
</ANNUAL_REPORT>

<SCHEMA>
{json.dumps(schema, indent=2)}
</SCHEMA>

Return ONLY valid JSON.
""".strip()

    resp = client.chat.completions.create(
        model=EXTRACTOR_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
    )
    return json.loads(resp.choices[0].message.content)


# ----------------------------
# Merge + post-processing
# ----------------------------

def deep_merge(preferred: Any, incoming: Any) -> Any:
    """
    Merge where incoming overwrites preferred only if it is meaningfully non-null.
    Lists: extend unique, preserve order.
    Dicts: recurse.
    """
    if isinstance(preferred, dict) and isinstance(incoming, dict):
        out = dict(preferred)
        for k, v in incoming.items():
            if k not in out:
                out[k] = v
            else:
                out[k] = deep_merge(out[k], v)
        return out

    if isinstance(preferred, list) and isinstance(incoming, list):
        seen = set()
        out = []
        for x in preferred + incoming:
            key = json.dumps(x, sort_keys=True) if isinstance(x, (dict, list)) else str(x)
            if key in seen:
                continue
            seen.add(key)
            out.append(x)
        return out

    # prefer incoming if it is not null/empty
    if incoming is None:
        return preferred
    if incoming == "" and preferred not in (None, ""):
        return preferred
    if incoming == [] and preferred != []:
        return preferred
    if incoming == {} and preferred != {}:
        return preferred

    return incoming


def compute_financial_changes(facts: Dict[str, Any]) -> None:
    fp = facts.get("financial_performance") or {}
    eps_c = fp.get("eps_current")
    eps_p = fp.get("eps_prior")
    # guard: reject years accidentally captured
    if isinstance(eps_p, (int, float)) and eps_p >= 1900:
        fp["eps_prior"] = None
        fp["eps_prior_source"] = None

    eps_c = fp.get("eps_current")
    eps_p = fp.get("eps_prior")
    if isinstance(eps_c, (int, float)) and isinstance(eps_p, (int, float)) and eps_p not in (0, None):
        fp["eps_change_pct"] = (eps_c - eps_p) / eps_p * 100.0
    else:
        fp["eps_change_pct"] = None

    prof_c = fp.get("profit_attributable_current_k")
    prof_p = fp.get("profit_attributable_prior_k")
    if isinstance(prof_c, (int, float)) and isinstance(prof_p, (int, float)) and prof_p not in (0, None):
        fp["profit_attributable_change_pct"] = (prof_c - prof_p) / prof_p * 100.0
    else:
        fp["profit_attributable_change_pct"] = None

    facts["financial_performance"] = fp


PAGE_RE = re.compile(r"\bPAGE\s+(\d+)\b", flags=re.IGNORECASE)

def extract_page_hints_from_sources(facts: Dict[str, Any]) -> List[int]:
    """
    Collect page numbers mentioned in any *_source fields; helps fill financial_source_pages_hint.
    """
    pages = set()

    def walk(x: Any):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and (k.endswith("_source") or "source" in k.lower()):
                    for m in PAGE_RE.finditer(v):
                        pages.add(int(m.group(1)))
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)

    walk(facts)
    return sorted(pages)


def finalize_fact_sheet(merged: Dict[str, Any], source_pdf: str) -> Dict[str, Any]:
    facts = deepcopy(FACT_SCHEMA_BASE)
    facts = deep_merge(facts, merged)

    facts["source_pdf"] = source_pdf

    # Fill financial_source_pages_hint if empty
    fp = facts.get("financial_performance") or {}
    if not fp.get("financial_source_pages_hint"):
        fp["financial_source_pages_hint"] = extract_page_hints_from_sources(fp)

    # Keep snippets if present, else try to map from sources
    facts["financial_performance"] = fp

    compute_financial_changes(facts)

    # Merge extraction notes
    if not isinstance(facts.get("extraction_notes"), str):
        facts["extraction_notes"] = ""

    return facts


# ----------------------------
# Public API
# ----------------------------

def extract_facts_multi_pass_from_pdf_to_dict(pdf_path: str) -> Dict[str, Any]:
    pages = read_pdf_pages(pdf_path)
    numbered = pages_to_numbered_text(pages, start_page_num=1)

    merged: Dict[str, Any] = {}
    notes: List[str] = []

    for pass_name, schema in MULTI_PASS:
        out = llm_extract(pass_name, schema, numbered)
        if isinstance(out, dict) and out.get("extraction_notes"):
            notes.append(f"[{pass_name}] {out.get('extraction_notes')}")
        merged = deep_merge(merged, out)

    merged_notes = "\n".join([n for n in notes if isinstance(n, str) and n.strip()])
    if "extraction_notes" in merged and isinstance(merged["extraction_notes"], str):
        merged["extraction_notes"] = (merged["extraction_notes"].strip() + "\n" + merged_notes).strip()
    else:
        merged["extraction_notes"] = merged_notes.strip()

    return finalize_fact_sheet(merged, source_pdf=os.path.basename(pdf_path))


def extract_facts_multi_pass_from_pdf(pdf_path: str, out_facts_path: str) -> None:
    facts = extract_facts_multi_pass_from_pdf_to_dict(pdf_path)
    with open(out_facts_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2)
    print(f"[OK] Saved multi-pass extracted facts to {out_facts_path}")




def extract_facts_multi_pass_from_pdf(pdf_path: str, out_facts_path: str) -> None:
    """
    Extract facts from the ENTIRE annual report PDF using multi-pass extraction,
    then write the final fact sheet to out_facts_path.
    """
    facts = extract_facts_multi_pass_from_pdf_to_dict(pdf_path)

    with open(out_facts_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2)

    print(f"[OK] Saved multi-pass extracted facts to {out_facts_path}")



if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python extract_facts_multi_pass.py <annual_report.pdf> <out_facts.json>")
        raise SystemExit(1)

    pdf_path = sys.argv[1]
    out_path = sys.argv[2]

    facts = extract_facts_multi_pass_from_pdf(pdf_path)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2)

    print(f"Saved multi-pass extracted facts to {out_path}")
