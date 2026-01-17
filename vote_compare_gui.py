# vote_compare_gui.py
"""
Streamlit GUI for compare_votes.py logic.

Run:
  pip install streamlit pandas openpyxl
  streamlit run vote_compare_gui.py
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional, Tuple

import pandas as pd
import streamlit as st


# ----------------------------
# Core logic (from your script)
# ----------------------------
def read_table_from_upload(upload) -> pd.DataFrame:
    """Read CSV/XLSX from a Streamlit uploaded file."""
    if upload is None:
        raise ValueError("No file uploaded")

    name = (upload.name or "").lower()
    ext = os.path.splitext(name)[1]

    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(upload)
    # CSV: handle common encodings
    try:
        return pd.read_csv(upload)
    except UnicodeDecodeError:
        upload.seek(0)
        return pd.read_csv(upload, encoding="latin1")


def norm_name(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def norm_vote(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    s = re.sub(r"\s+", " ", s)

    for_pat = ["for", "in favour", "in favor", "support", "approve", "yes", "vote for"]
    against_pat = ["against", "oppose", "no", "vote against", "reject", "not support"]
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

    return s.upper()


def build_vote_lookup(df: pd.DataFrame, name_col: str, vote_col: str) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for _, row in df.iterrows():
        name = norm_name(row.get(name_col))
        vote = norm_vote(row.get(vote_col))
        if not name:
            continue
        if name not in lookup:
            lookup[name] = vote
        else:
            if (not lookup[name]) and vote:
                lookup[name] = vote
    return lookup


def load_mapping_df(mdf: pd.DataFrame, pred_key_col: str, true_key_col: str) -> Dict[str, Optional[str]]:
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
    total_pred = 0
    compared = 0
    auto_correct_no_match = 0
    matches_total = 0

    for_match = 0
    against_match = 0
    for_total_compared = 0
    against_total_compared = 0

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

        mapped_true_name = mapping.get(pred_name, None)

        if mapped_true_name is None:
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
        "for_match": for_match,
        "for_total_compared": for_total_compared,
        "for_accuracy": (for_match / for_total_compared) if for_total_compared else None,
        "against_match": against_match,
        "against_total_compared": against_total_compared,
        "against_accuracy": (against_match / against_total_compared) if against_total_compared else None,
        "confusion_FOR->FOR": conf[("FOR", "FOR")],
        "confusion_FOR->AGAINST": conf[("FOR", "AGAINST")],
        "confusion_AGAINST->FOR": conf[("AGAINST", "FOR")],
        "confusion_AGAINST->AGAINST": conf[("AGAINST", "AGAINST")],
    }
    return details, summary


# -------------
# Streamlit GUI
# -------------
st.set_page_config(page_title="Vote Comparator", layout="wide")
st.title("Vote Comparator (True vs Predicted)")

st.markdown(
    """
Upload your files, select the relevant columns, and click **Compare**.
Rule enforced: if a predicted investor has **no match** in the mapping, it is counted as **AUTO_CORRECT_NO_MATCH**.
"""
)

colA, colB, colC = st.columns(3)
with colA:
    true_file = st.file_uploader("TRUE votes file (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="true")
with colB:
    pred_file = st.file_uploader("PREDICTED votes file (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="pred")
with colC:
    map_file = st.file_uploader("NAME mapping file (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="map")

true_df = pred_df = map_df = None

if true_file and pred_file and map_file:
    try:
        true_df = read_table_from_upload(true_file)
        pred_df = read_table_from_upload(pred_file)
        map_df = read_table_from_upload(map_file)
    except Exception as e:
        st.error(f"Failed to read one of the files: {e}")
        st.stop()

    st.subheader("Select columns")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.caption("TRUE file columns")
        true_name_col = st.selectbox("True: investor name column", options=list(true_df.columns), index=0)
        true_vote_col = st.selectbox("True: vote column", options=list(true_df.columns), index=min(1, len(true_df.columns)-1))

    with c2:
        st.caption("PRED file columns")
        pred_name_col = st.selectbox("Pred: investor name column", options=list(pred_df.columns), index=0)
        pred_vote_col = st.selectbox("Pred: vote column", options=list(pred_df.columns), index=min(1, len(pred_df.columns)-1))

    with c3:
        st.caption("Mapping file columns")
        # Smart defaults if your common names exist
        map_pred_default = "Investor_df2" if "Investor_df2" in map_df.columns else map_df.columns[0]
        map_true_default = "Matched_df1" if "Matched_df1" in map_df.columns else map_df.columns[min(1, len(map_df.columns)-1)]

        map_pred_col = st.selectbox(
            "Map: predicted-name column",
            options=list(map_df.columns),
            index=list(map_df.columns).index(map_pred_default),
        )
        map_true_col = st.selectbox(
            "Map: true-name column",
            options=list(map_df.columns),
            index=list(map_df.columns).index(map_true_default),
        )

    st.divider()

    # Optional: show previews
    with st.expander("Preview uploaded dataframes"):
        tcol, pcol, mcol = st.columns(3)
        with tcol:
            st.write("TRUE (head)")
            st.dataframe(true_df.head(20), use_container_width=True)
        with pcol:
            st.write("PRED (head)")
            st.dataframe(pred_df.head(20), use_container_width=True)
        with mcol:
            st.write("MAP (head)")
            st.dataframe(map_df.head(20), use_container_width=True)

    if st.button("Compare", type="primary"):
        try:
            mapping = load_mapping_df(map_df, map_pred_col, map_true_col)
            details, summary = compare_votes(
                true_df=true_df,
                pred_df=pred_df,
                mapping=mapping,
                true_name_col=true_name_col,
                true_vote_col=true_vote_col,
                pred_name_col=pred_name_col,
                pred_vote_col=pred_vote_col,
            )
        except Exception as e:
            st.error(f"Comparison failed: {e}")
            st.stop()

        st.success("Done!")

        st.subheader("Summary")
        # Pretty summary display
        summary_df = pd.DataFrame(list(summary.items()), columns=["metric", "value"])
        st.dataframe(summary_df, use_container_width=True)

        st.subheader("Row-level details")
        st.dataframe(details, use_container_width=True, height=450)

        csv_bytes = details.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download details CSV",
            data=csv_bytes,
            file_name="vote_compare_details.csv",
            mime="text/csv",
        )

else:
    st.info("Upload TRUE, PREDICTED, and MAP files to begin.")
