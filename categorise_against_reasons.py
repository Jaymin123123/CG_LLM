import json
import pandas as pd
from config import client, EXTRACT_MODEL

IN_PATH = "against_reasons_long.csv"
OUT_PATH = "gainst_reasons_categorised.csv"

SYSTEM_PROMPT = """
You categorise investor AGAINST reasons for remuneration resolutions.

Choose ALL applicable categories from the provided list.
Do not invent new categories.
Return strict JSON only.

Categories:
- PAY_FOR_PERFORMANCE_FAILURE
- EXCESSIVE_TOTAL_PAY
- EXCESSIVE_VARIABLE_PAY
- ONE_OFF_OR_RETENTION_AWARD
- ACCELERATED_VESTING_OR_LEAVERS
- DILUTION_CONCERNS
- WEAK_OR_NO_PERFORMANCE_TARGETS
- WEAK_GOVERNANCE_STRUCTURES
- INSUFFICIENT_DISCLOSURE
- ESG_LINKAGE_INADEQUATE
"""

df = pd.read_csv(IN_PATH)

categories = []

for idx, row in df.iterrows():
    reason = row["against_reason"]

    if not isinstance(reason, str) or not reason.strip():
        categories.append([])
        continue

    resp = client.chat.completions.create(
        model=EXTRACT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": reason},
        ],
        temperature=0.0,
    )

    cats = json.loads(resp.choices[0].message.content).get("categories", [])
    categories.append(cats)

df["reason_categories"] = categories
df.to_csv(OUT_PATH, index=False)

print("Saved:", OUT_PATH)
print(df[["investor", "reason_categories"]].head(5))
