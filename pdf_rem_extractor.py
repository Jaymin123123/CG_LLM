import re
from typing import List, Tuple, Optional
from PyPDF2 import PdfReader


REM_REPORT_PATTERNS = [
    r"remuneration report",                  # generic
    r"remuneration report of the remuneration committee",
    r"directors'? remuneration report",
]

REM_END_PATTERNS = [
    r"\bfinancial statements\b",
    r"\bindependent auditor'?s report\b",
    r"\bnotes to the consolidated financial statements\b",
    r"\bconsolidated financial statements\b",
]


def load_pdf_pages(pdf_path: str) -> List[str]:
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
    return pages


def find_rem_candidate_indices(pages: List[str]) -> List[int]:
    candidates = []
    for idx, text in enumerate(pages):
        lower = text.lower()
        for pat in REM_REPORT_PATTERNS:
            if re.search(pat, lower, flags=re.IGNORECASE):
                candidates.append(idx)
                break
    return candidates


def score_candidate(pages: List[str], idx: int, window: int = 5) -> Tuple[int, int]:
    """
    Score a candidate page by:
    - rem_count: number of 'remuneration' occurrences in page idx..idx+window
    - word_count: total words in that window
    """
    start = idx
    end = min(len(pages), idx + window)
    txt = "\n".join(pages[start:end])
    rem_count = len(re.findall(r"remuneration", txt, flags=re.IGNORECASE))
    word_count = len(txt.split())
    return rem_count, word_count


def choose_best_rem_start(pages: List[str]) -> Optional[int]:
    candidates = find_rem_candidate_indices(pages)
    if not candidates:
        return None

    # Ignore very early pages (likely table of contents)
    candidates = [i for i in candidates if i >= 5] or candidates

    scored = []
    for idx in candidates:
        rem_count, word_count = score_candidate(pages, idx)
        scored.append((idx, rem_count, word_count))

    # Sort by: highest rem_count, then highest word_count, then highest page index
    scored.sort(key=lambda t: (t[1], t[2], t[0]), reverse=True)
    best_idx, best_rem_count, best_word_count = scored[0]

    print("Rem candidates:")
    for idx, rc, wc in scored:
        print(f"  page {idx+1}: rem_count={rc}, word_count={wc}")
    print(f"Chosen start page: {best_idx+1}")

    return best_idx


import re
from typing import List, Optional


# Words/phrases that strongly suggest we are still in the remuneration / pay section
REM_KEYWORDS = [
    r"\bremuneration\b",
    r"\bcompensation\b",
    r"\bdirectors'? remuneration\b",
    r"\bexecutive remuneration\b",
    r"\bmanaging board\b",
    r"\bsupervisory board\b",
    r"\bboard remuneration\b",
    r"\bnon[- ]executive director\b",
    r"\bbase salary\b",
    r"\bannual fixed salary\b",
    r"\bbonus\b",
    r"\bshort[- ]term incentive\b",
    r"\blong[- ]term incentive\b",
    r"\bltip\b",
    r"\bstip\b",
    r"\btotal cash\b",
    r"\bpay ratio\b",
    r"\btermination benefit\b",
    r"\bseverance\b",
]

# Words/phrases that strongly suggest we've moved on to another big section
BREAK_KEYWORDS = [
    r"\bconsolidated financial statements\b",
    r"\bseparate financial statements\b",
    r"\bfinancial statements\b",
    r"\bnotes to the (consolidated )?financial statements\b",
    r"\bindependent auditor'?s report\b",
    r"\bauditor'?s report\b",
    r"\brisk management\b",
    r"\brisk factors\b",
    r"\bcorporate responsibility\b",
    r"\bsustainability report\b",
    r"\bnon[- ]financial statement\b",
    r"\bmanagement report\b",
    r"\bselected financial information\b",
]


def _score_page(text: str) -> tuple[int, int]:
    """
    Return (rem_score, break_score) for a page:
    - rem_score: how 'remuneration-like' it is
    - break_score: how much it looks like we've moved into another major section
    """
    lower = text.lower()

    rem_score = 0
    for pat in REM_KEYWORDS:
        rem_score += len(re.findall(pat, lower))

    break_score = 0
    for pat in BREAK_KEYWORDS:
        break_score += len(re.findall(pat, lower))

    return rem_score, break_score


def find_end_page(
    pages: List[str],
    start_idx: int,
    max_pages: int = 40,
    min_pages: int = 3,
    max_gap_without_rem: int = 3,
) -> int:
    """
    Heuristic, issuer-agnostic end-of-remuneration-section detector.

    Strategy:
    - Walk forward from start_idx.
    - Track the last page index that still looks 'remuneration-like'.
    - If we see several pages in a row with no remuneration signal AND
      we see one or more strong 'break' cues (financial statements, auditor, risk, etc.),
      we assume the remuneration section has ended.
    - Also stop if we hit max_pages after start_idx.

    Returns the index of the *last remuneration page* (0-based).
    """
    last_idx = min(len(pages) - 1, start_idx + max_pages)
    last_rem_like_idx = start_idx

    gap_without_rem = 0

    for idx in range(start_idx, last_idx + 1):
        text = pages[idx] or ""
        rem_score, break_score = _score_page(text)

        # Treat this as 'remuneration-like' if we see any relevant words at all
        if rem_score > 0:
            last_rem_like_idx = idx
            gap_without_rem = 0
        else:
            gap_without_rem += 1

        # Only consider breaking once we've gone past a minimum number of pages
        if idx >= start_idx + min_pages:
            # Heuristic break condition:
            # - we've gone several pages without any remuneration signals
            # - AND we see at least one strong break cue on this page
            if gap_without_rem >= max_gap_without_rem and break_score > 0:
                # End just before current 'new section' page
                return max(last_rem_like_idx, start_idx)

    # Fallback: no clear break found, return last rem-like page we saw
    return max(last_rem_like_idx, start_idx)





def extract_rem_section_from_pdf(pdf_path: str) -> Tuple[str, int, int]:
    """
    Returns (rem_text, start_page_index, end_page_index).
    Page indices are 0-based.
    """
    pages = load_pdf_pages(pdf_path)

    start_page = choose_best_rem_start(pages)
    if start_page is None:
        raise ValueError("Could not find any Remuneration Report section in this PDF.")

    end_page = find_end_page(pages, start_page)

    rem_text = "\n\n".join(pages[start_page:end_page + 1])
    return rem_text, start_page, end_page


if __name__ == "__main__":
    import sys
    pdf_path = sys.argv[1]

    rem_text, start_idx, end_idx = extract_rem_section_from_pdf(pdf_path)
    print(f"Remuneration section pages ~ {start_idx+1}–{end_idx+1}")
    print(rem_text[:2000])
