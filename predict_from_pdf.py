# predict_from_pdf.py

import os
import sys
import json

from pipeline_extract_from_pdf import extract_facts_from_full_pdf
from judge_investors import judge_all_investors


def main(pdf_path: str, investor_csv_path: str, output_csv_path: str):
    # 1) Choose a temp facts path next to the PDF
    base_dir = os.path.dirname(os.path.abspath(pdf_path))
    facts_path = os.path.join(base_dir, "facts.json")

    # 2) Extract + postprocess facts for this PDF
    print(f"[1/2] Extracting remuneration facts from {pdf_path} ...")
    extract_facts_from_full_pdf(pdf_path, facts_path)

    # Optional: quick peek
    with open(facts_path, "r", encoding="utf-8") as f:
        facts = json.load(f)
    print(f"Extracted facts for company: {facts.get('company_name')} ({facts.get('financial_year')})")
    print(f"Rem pages: {facts.get('rem_pages_start')}–{facts.get('rem_pages_end')}")

    # 3) Run investor-level predictions
    print(f"[2/2] Judging all investors in {investor_csv_path} ...")
    judge_all_investors(investor_csv_path, facts_path, output_csv_path)

    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python predict_from_pdf.py 'Annual Report.pdf' investor_policies.csv investor_votes.csv")
        raise SystemExit(1)

    pdf_path = sys.argv[1]
    investor_csv_path = sys.argv[2]
    output_csv_path = sys.argv[3]

    main(pdf_path, investor_csv_path, output_csv_path)
