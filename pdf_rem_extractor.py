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


def find_end_page(pages, start_idx, max_pages=30):
    """
    Scan forward until we hit:
    - clear start of Financial Statements / Auditors' report, OR
    - section '5.' (next chapter), OR
    - we hit max_pages after start_idx.
    """
    last_idx = min(len(pages) - 1, start_idx + max_pages)
    for idx in range(start_idx + 1, last_idx + 1):
        lower = pages[idx].lower()
        if ("financial statements" in lower 
            or "independent auditor" in lower 
            or re.search(r"^\s*5\.\d", lower, flags=re.MULTILINE)):
            return idx - 1
    return last_idx



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
