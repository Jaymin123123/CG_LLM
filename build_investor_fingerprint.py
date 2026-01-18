import json
import pandas as pd
from collections import Counter

IN_PATH = "against_reasons_categorised_updated.csv"
OUT_PATH = "investor_fingerprints.json"

df = pd.read_csv(IN_PATH)

# Only AGAINST votes matter for the fingerprint triggers
df = df[df["vote"].astype(str).str.upper() == "AGAINST"].copy()

def parse_categories(x):
    if isinstance(x, list):
        return x
    if not isinstance(x, str):
        return []
    x = x.strip()
    if not x or x == "[]":
        return []
    try:
        return json.loads(x.replace("'", '"'))  # handles list stored as string
    except Exception:
        try:
            return eval(x)  # last resort for strings like "['A','B']"
        except Exception:
            return []

df["cats"] = df["reason_categories"].apply(parse_categories)

fingerprints = {}

for investor, g in df.groupby("investor"):
    all_cats = []
    examples = []

    for _, row in g.iterrows():
        all_cats.extend(row["cats"])
        txt = row.get("against_reason", "")
        if isinstance(txt, str) and txt.strip() and txt.strip().lower() != "no comments available":
            examples.append(txt.strip())

    counter = Counter(all_cats)
    total = sum(counter.values()) or 1

    top_triggers = [
        {"category": k, "weight": round(v / total, 3), "count": int(v)}
        for k, v in counter.most_common(6)
    ]

    p4p_count = counter["PAY_FOR_PERFORMANCE_FAILURE"]
    disclosure_count = counter["INSUFFICIENT_DISCLOSURE"] + counter["WEAK_OR_NO_PERFORMANCE_TARGETS"]
    excessive_pay_count = counter["EXCESSIVE_TOTAL_PAY"] + counter["EXCESSIVE_VARIABLE_PAY"]

    # Soft priors (can guide reasoning)
    pay_for_performance_sensitive = (p4p_count >= 1)
    disclosure_sensitive = (disclosure_count >= 1)
    leavers_sensitive = (counter["ACCELERATED_VESTING_OR_LEAVERS"] >= 1)
    one_offs_sensitive = (counter["ONE_OFF_OR_RETENTION_AWARD"] >= 1)
    excessive_pay_sensitive = (excessive_pay_count >= 1)

    # HARD gate for applying the strict pay-for-performance override
    # Require enough history so we don't over-trigger
    n_reasons = len(examples)
    p4p_share = p4p_count / total if total else 0.0

    pay_for_performance_strong = (
        n_reasons >= 5 and
        p4p_count >= 3 and
        p4p_share >= 0.25
    )

    fingerprints[investor] = {
        "n_against_with_reasons": n_reasons,
        "top_triggers": top_triggers,
        "example_phrases": examples[:3],

        # soft priors
        "pay_for_performance_sensitive": pay_for_performance_sensitive,
        "disclosure_sensitive": disclosure_sensitive,
        "leavers_sensitive": leavers_sensitive,
        "one_offs_sensitive": one_offs_sensitive,
        "excessive_pay_sensitive": excessive_pay_sensitive,

        # hard gate
        "pay_for_performance_strong": pay_for_performance_strong,

        # helpful debug fields
        "p4p_count": int(p4p_count),
        "p4p_share": round(float(p4p_share), 3),
        "total_category_hits": int(total),
    }


with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(fingerprints, f, indent=2)

print("Saved:", OUT_PATH)
print("Example Aberdeen fingerprint:")
print(json.dumps(fingerprints.get("Aberdeen Asset Managers Ltd.Standard Life"), indent=2))
