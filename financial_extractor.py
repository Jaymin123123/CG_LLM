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

    # Find pages likely containing financial statements (broader search)
    financial_statement_pages = _find_page_indices(
        pages,
        patterns=[
            r"consolidated statement of (comprehensive )?income",
            r"consolidated income statement",
            r"statement of comprehensive income",
            r"income statement",
            r"consolidated statement of financial position",
            r"consolidated statement of profit or loss",
            r"financial statements",
        ],
    )

    # Also find pages with EPS mentions
    eps_pages = _find_page_indices(
        pages,
        patterns=[
            r"basic and diluted earnings per share",
            r"\beps\b",
            r"earnings per share",
        ],
    )

    # Combine and deduplicate page indices
    candidate_pages = sorted(set(financial_statement_pages + eps_pages))

    # We'll scan a larger window around each hit and pick the best match
    best = {
        "eps_current": None,
        "eps_prior": None,
        "profit_current_k": None,
        "profit_prior_k": None,
        "source_pages": [],
        "sources": {},
    }

    # regexes: more flexible patterns to handle various table formats
    # EPS pattern: looks for "earnings per share" followed by numbers (handles tables with years/columns)
    eps_line_re = re.compile(
        r"(?:basic(?:\s+and\s+diluted)?\s+)?earnings\s+per\s+share[^\d]*?(?:[0-9]{4}[^\d]*?)?([0-9]+(?:\.[0-9]+)?)[^\d]+([0-9]+(?:\.[0-9]+)?)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    
    # Alternative EPS pattern for table formats: "EPS" or "Earnings per share" with numbers in same line or nearby
    eps_line_re_alt = re.compile(
        r"earnings\s+per\s+share[:\s]*\n?[^\d]*?([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    # More flexible profit regex - handles various formats
    profit_line_re = re.compile(
        r"profit\s+(?:attributable\s+to|for\s+the\s+year|after\s+tax)[^\d]*?(?:\(?€?\s*000\)?|\(?€?\s*m\)?|\(?€?\s*k\)?)?[^\d]*?([0-9]{1,3}(?:[,.\s][0-9]{3})*)\s+([0-9]{1,3}(?:[,.\s][0-9]{3})*)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Search with expanded windows around financial statement pages
    for idx in candidate_pages:
        # Use a much larger window: 10 pages before and 20 pages after
        # Financial statements can span multiple pages
        window_start = max(0, idx - 10)
        window_end = min(len(pages), idx + 20)
        window_text = "\n".join(pages[window_start:window_end])

        eps_m = eps_line_re.search(window_text)
        if not eps_m:
            eps_m = eps_line_re_alt.search(window_text)
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
                "eps_source_snippet": window_text[window_text.lower().find("earnings per share"):][:500] if "earnings per share" in window_text.lower() else None,
                "profit_source_snippet": (window_text[window_text.lower().find("profit"):][:500]
                                          if "profit" in window_text.lower() else None),
            }
            break  # good enough for v1
    
    # If we didn't find EPS in the windows, try searching the entire PDF
    if best["eps_current"] is None:
        full_text = "\n".join(pages)
        eps_m = eps_line_re.search(full_text)
        if not eps_m:
            eps_m = eps_line_re_alt.search(full_text)
        prof_m = profit_line_re.search(full_text)
        
        if eps_m:
            eps_current = _parse_number(eps_m.group(1))
            eps_prior = _parse_number(eps_m.group(2))
            
            profit_current_k = None
            profit_prior_k = None
            if prof_m:
                profit_current_k = _parse_number(prof_m.group(1))
                profit_prior_k = _parse_number(prof_m.group(2))
            
            best["eps_current"] = eps_current
            best["eps_prior"] = eps_prior
            best["profit_current_k"] = profit_current_k
            best["profit_prior_k"] = profit_prior_k
            best["source_pages"] = ["full_pdf_search"]
            best["sources"] = {
                "eps_source_snippet": full_text[full_text.lower().find("earnings per share"):][:500] if "earnings per share" in full_text.lower() else None,
                "profit_source_snippet": (full_text[full_text.lower().find("profit"):][:500]
                                          if "profit" in full_text.lower() else None),
            }

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
