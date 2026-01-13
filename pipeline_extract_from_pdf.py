# pipeline_extract_from_pdf.py

import json
import sys
from financial_extractor import extract_financial_performance
from pdf_rem_extractor import extract_rem_section_from_pdf
from extract_facts import extract_facts_from_report
from postprocess_facts import postprocess_facts   # <-- ADD THIS IMPORT


def extract_facts_from_full_pdf(pdf_path: str, output_json_path: str):
    rem_text, start_idx, end_idx = extract_rem_section_from_pdf(pdf_path)
    print(f"Candidate Rem section pages {start_idx+1}–{end_idx+1}")
    print("Preview:\n", rem_text[:1000])

    # 1️⃣ Run LLM fact extractor
    facts = extract_facts_from_report(rem_text)

    # 2️⃣ Add metadata
    facts.setdefault("source_pdf", pdf_path)
    facts.setdefault("rem_pages_start", start_idx + 1)
    facts.setdefault("rem_pages_end", end_idx + 1)
    
    # Add financial performance (separate pass across the whole PDF)
    facts["financial_performance"] = extract_financial_performance(pdf_path)
    print("Extracted financial_performance:", facts["financial_performance"])

    # Then postprocess as usual
    facts = postprocess_facts(facts)

    # 3️⃣ **** RUN THE POST-PROCESSOR HERE ****
    facts = postprocess_facts(facts)

    # 4️⃣ Save final enriched JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2)

    print(f"Saved facts to {output_json_path}")


if __name__ == "__main__":
    pdf_path = sys.argv[1]
    out_path = sys.argv[2]
    extract_facts_from_full_pdf(pdf_path, out_path)
