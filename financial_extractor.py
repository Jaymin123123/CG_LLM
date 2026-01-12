# financial_extractor.py
import re
from typing import Dict, Any, List, Optional
from PyPDF2 import PdfReader


def _read_pdf_pages(pdf_path: str) -> List[str]:
    reader = PdfReader(pdf_path)
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def _find_page_indices(pages: List[str], patterns: List[str]) -> List[int]:
    hits = []
    for i, t in enumerate(pages):
        low = (t or "").lower()
        if any(re.search(pat, low, flags=re.IGNORECASE) for pat in patterns):
            hits.append(i)
    return hits


def _parse_number(s: str) -> Optional[float]:
    if s is None:
        return None
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except Exception:
        return None


def extract_financial_performance(pdf_path: str) -> Dict[str, Any]:
    """
    Extract a minimal set of financial performance metrics from the PDF,
    focusing on items commonly used in remuneration "pay-for-performance" arguments.

    Currently targets:
      - basic/diluted EPS current and prior year
      - profit attributable (if present near EPS table)

    Returns a dict suitable to merge into facts.json as:
      facts["financial_performance"] = {...}
    """
    pages = _read_pdf_pages(pdf_path)

    # Find pages likely containing EPS tables
    eps_pages = _find_page_indices(
        pages,
        patterns=[
            r"basic and diluted earnings per share",
            r"\beps\b",
            r"earnings per share",
        ],
    )

    # We'll scan a small window around each hit and pick the best match
    best = {
        "eps_current": None,
        "eps_prior": None,
        "profit_current_k": None,
        "profit_prior_k": None,
        "source_pages": [],
        "sources": {},
    }

    # regexes: allow "Dec-24 Dec-23 0.24 0.39" or variants
    eps_line_re = re.compile(
        r"basic and diluted earnings per share.*?\n.*?([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    profit_line_re = re.compile(
        r"profit attributable.*?\(?€\s*000\)?.*?\n.*?([0-9]{1,3}(?:,[0-9]{3})*)\s+([0-9]{1,3}(?:,[0-9]{3})*)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    for idx in eps_pages:
        window_start = max(0, idx - 1)
        window_end = min(len(pages), idx + 2)
        window_text = "\n".join(pages[window_start:window_end])

        eps_m = eps_line_re.search(window_text)
        prof_m = profit_line_re.search(window_text)

        # Heuristic: prefer candidates where we found EPS
        if eps_m:
            eps_current = _parse_number(eps_m.group(1))
            eps_prior = _parse_number(eps_m.group(2))

            # Try profit too
            profit_current_k = None
            profit_prior_k = None
            if prof_m:
                profit_current_k = _parse_number(prof_m.group(1))
                profit_prior_k = _parse_number(prof_m.group(2))

            # Pick the first solid EPS match; you can enhance scoring later
            best["eps_current"] = eps_current
            best["eps_prior"] = eps_prior
            best["profit_current_k"] = profit_current_k
            best["profit_prior_k"] = profit_prior_k
            best["source_pages"] = [window_start + 1, idx + 1, window_end]  # human-ish
            best["sources"] = {
                "eps_source_snippet": window_text[window_text.lower().find("basic and diluted earnings per share"):][:250],
                "profit_source_snippet": (window_text[window_text.lower().find("profit attributable") :][:250]
                                          if "profit attributable" in window_text.lower() else None),
            }
            break  # good enough for v1

    # Compute changes deterministically
    eps_change_pct = None
    if best["eps_current"] is not None and best["eps_prior"] not in (None, 0):
        eps_change_pct = (best["eps_current"] - best["eps_prior"]) / best["eps_prior"] * 100.0

    profit_change_pct = None
    if best["profit_current_k"] is not None and best["profit_prior_k"] not in (None, 0):
        profit_change_pct = (best["profit_current_k"] - best["profit_prior_k"]) / best["profit_prior_k"] * 100.0

    return {
        "eps_current": best["eps_current"],
        "eps_prior": best["eps_prior"],
        "eps_change_pct": eps_change_pct,
        "profit_attributable_current_k": best["profit_current_k"],
        "profit_attributable_prior_k": best["profit_prior_k"],
        "profit_attributable_change_pct": profit_change_pct,
        "financial_source_pages_hint": best["source_pages"],
        "financial_sources": best["sources"],
    }
