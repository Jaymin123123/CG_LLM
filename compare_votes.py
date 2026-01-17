# compare_votes.py
"""
Compare votes between a "true" spreadsheet and a "predicted" spreadsheet using a name-matching map.

Key rule (as requested):
- If a predicted investor name has NO match in the mapping file, we count it as a CORRECT vote automatically.

Expected mapping file format (your uploaded one fits this):
- Column: Investor_df2   -> name as it appears in the predicted sheet
- Column: Matched_df1    -> corresponding name in the true sheet (may be blank/NaN if no match)

Usage example:
python compare_votes.py \
  --true true_votes.csv --pred predicted_votes.csv \
  --map name_matching_results_one_to_one.csv \
  --true-name-col Investor --true-vote-col Vote \
  --pred-name-col Investor --pred-vote-col Vote \
  --out details.csv

Notes:
- Supports CSV and Excel (.xlsx).
- Normalises votes (e.g., "FOR", "For ", "in favour" -> "FOR"; "against", "oppose" -> "AGAINST").
"""

from __future__ import annotations

import argparse
import os
import re
from typing import Dict, Optional, Tuple

import pandas as pd


def read_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path.lower())[1]
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(path)
    return pd.read_csv(path)


def norm_name(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def norm_vote(x) -> str:
    """
    Normalise vote labels to a small set. Extend this mapping if your data has more categories.
    """
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    s = re.sub(r"\s+", " ", s)

    # Common mappings
    for_pat = [
        "for",
        "in favour",
        "in favor",
        "support",
        "approve",
        "yes",
        "vote for",
    ]
    against_pat = [
        "against",
        "oppose",
        "no",
        "vote against",
        "reject",
        "not support",
    ]
    abstain_pat = ["abstain", "abstention"]
    withhold_pat = ["withhold", "withheld"]
    na_pat = ["n/a", "na", "none", "not voted", "not vote", "did not vote", "dnp"]

    if any(p in s for p in for_pat):
        return "FOR"
    if any(p in s for p in against_pat):
        return "AGAINST"
    if any(p in s for p in abstain_pat):
        return "ABSTAIN"
    if any(p in s for p in withhold_pat):
        return "WITHHOLD"
    if any(p in s for p in na_pat):
        return "NA"

    # Fallback: keep uppercased cleaned string
    return s.upper()


def build_vote_lookup(df: pd.DataFrame, name_col: str, vote_col: str) -> Dict[str, str]:
    """
    Build name -> vote lookup. If duplicates exist, the first non-empty vote wins.
    """
    lookup: Dict[str, str] = {}
    for _, row in df.iterrows():
        name = norm_name(row.get(name_col))
        vote = norm_vote(row.get(vote_col))
        if not name:
            continue
        if name not in lookup:
            lookup[name] = vote
        else:
            # If existing is empty and new is not, update
            if (not lookup[name]) and vote:
                lookup[name] = vote
    return lookup


def load_mapping(map_path: str, pred_key_col: str, true_key_col: str) -> Dict[str, Optional[str]]:
    """
    pred_name -> true_name (or None if no match)
    """
    mdf = read_table(map_path)
    if pred_key_col not in mdf.columns or true_key_col not in mdf.columns:
        raise ValueError(
            f"Mapping file must contain columns '{pred_key_col}' and '{true_key_col}'. "
            f"Found: {list(mdf.columns)}"
        )

    mapping: Dict[str, Optional[str]] = {}
    for _, r in mdf.iterrows():
        pred_name = norm_name(r.get(pred_key_col))
        true_name = norm_name(r.get(true_key_col))
        if not pred_name:
            continue
        mapping[pred_name] = true_name if true_name else None
    return mapping


def compare_votes(
    true_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    true_name_col: str,
    true_vote_col: str,
    pred_name_col: str,
    pred_vote_col: str,
) -> Tuple[pd.DataFrame, dict]:
    true_lookup = build_vote_lookup(true_df, true_name_col, true_vote_col)

    rows = []
    # Summary counters
    total_pred = 0
    compared = 0  # actually compared (i.e., had a match and found true vote)
    auto_correct_no_match = 0
    matches_total = 0

    # For/Against match counters (your requested score)
    for_match = 0
    against_match = 0
    for_total_compared = 0
    against_total_compared = 0

    # Confusion counts (only for FOR/AGAINST when compared)
    conf = {
        ("FOR", "FOR"): 0,
        ("FOR", "AGAINST"): 0,
        ("AGAINST", "FOR"): 0,
        ("AGAINST", "AGAINST"): 0,
    }

    for _, r in pred_df.iterrows():
        total_pred += 1

        pred_name = norm_name(r.get(pred_name_col))
        pred_vote = norm_vote(r.get(pred_vote_col))

        mapped_true_name = mapping.get(pred_name, None)  # None => no match / unknown

        if mapped_true_name is None:
            # Rule: if no match, treat as correct
            auto_correct_no_match += 1
            matches_total += 1
            rows.append(
                {
                    "pred_name": pred_name,
                    "mapped_true_name": "",
                    "true_vote": "",
                    "pred_vote": pred_vote,
                    "status": "AUTO_CORRECT_NO_MATCH",
                    "is_match": True,
                }
            )
            continue

        true_vote = true_lookup.get(mapped_true_name, "")
        compared += 1

        is_match = (true_vote == pred_vote) and (true_vote != "" or pred_vote != "")
        if is_match:
            matches_total += 1

        # Count FOR/AGAINST scoring only when we have a comparable class on both sides
        if true_vote in ("FOR", "AGAINST") and pred_vote in ("FOR", "AGAINST"):
            if true_vote == "FOR":
                for_total_compared += 1
                if pred_vote == "FOR":
                    for_match += 1
            if true_vote == "AGAINST":
                against_total_compared += 1
                if pred_vote == "AGAINST":
                    against_match += 1
            conf[(true_vote, pred_vote)] += 1

        rows.append(
            {
                "pred_name": pred_name,
                "mapped_true_name": mapped_true_name,
                "true_vote": true_vote,
                "pred_vote": pred_vote,
                "status": "MATCH" if is_match else "MISMATCH",
                "is_match": bool(is_match),
            }
        )

    details = pd.DataFrame(rows)

    summary = {
        "total_pred_rows": total_pred,
        "auto_correct_no_match": auto_correct_no_match,
        "compared_rows_with_match": compared,
        "matches_total_including_auto": matches_total,
        "accuracy_including_auto": (matches_total / total_pred) if total_pred else 0.0,
        # Your requested “score” split:
        "for_match": for_match,
        "for_total_compared": for_total_compared,
        "for_accuracy": (for_match / for_total_compared) if for_total_compared else None,
        "against_match": against_match,
        "against_total_compared": against_total_compared,
        "against_accuracy": (against_match / against_total_compared) if against_total_compared else None,
        # Confusion (FOR/AGAINST only, compared rows)
        "confusion_FOR->FOR": conf[("FOR", "FOR")],
        "confusion_FOR->AGAINST": conf[("FOR", "AGAINST")],
        "confusion_AGAINST->FOR": conf[("AGAINST", "FOR")],
        "confusion_AGAINST->AGAINST": conf[("AGAINST", "AGAINST")],
    }
    return details, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--true", required=True, help="Path to TRUE votes spreadsheet (csv/xlsx)")
    ap.add_argument("--pred", required=True, help="Path to PREDICTED votes spreadsheet (csv/xlsx)")
    ap.add_argument("--map", required=True, help="Path to name matching map (csv/xlsx)")

    ap.add_argument("--true-name-col", required=True, help="Column name for investor name in TRUE file")
    ap.add_argument("--true-vote-col", required=True, help="Column name for vote in TRUE file")
    ap.add_argument("--pred-name-col", required=True, help="Column name for investor name in PRED file")
    ap.add_argument("--pred-vote-col", required=True, help="Column name for vote in PRED file")

    # Defaults match your uploaded mapping file
    ap.add_argument("--map-pred-col", default="Investor_df2", help="Pred name col in mapping file")
    ap.add_argument("--map-true-col", default="Matched_df1", help="True name col in mapping file")

    ap.add_argument("--out", default="vote_compare_details.csv", help="Output CSV path for row-level details")

    args = ap.parse_args()

    true_df = read_table(args.true)
    pred_df = read_table(args.pred)
    mapping = load_mapping(args.map, args.map_pred_col, args.map_true_col)

    details, summary = compare_votes(
        true_df=true_df,
        pred_df=pred_df,
        mapping=mapping,
        true_name_col=args.true_name_col,
        true_vote_col=args.true_vote_col,
        pred_name_col=args.pred_name_col,
        pred_vote_col=args.pred_vote_col,
    )

    details.to_csv(args.out, index=False)

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    print(f"\nWrote row-level details to: {args.out}")


if __name__ == "__main__":
    main()
