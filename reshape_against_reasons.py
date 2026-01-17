import pandas as pd
import re

IN_PATH = "against_reasons.csv"
OUT_PATH = "against_reasons_long.csv"

df = pd.read_csv(IN_PATH, encoding="cp1252")


# Base columns (issuer + resolution title)
base_cols = []
for c in ["ISSUER", "full_name", "Resolution", "Proposal"]:
    if c in df.columns:
        base_cols.append(c)

cols = list(df.columns)

pairs = []
i = 0
while i < len(cols) - 1:
    col = cols[i]
    nxt = cols[i + 1]

    # Heuristic: investor name column followed by "Against comment"
    if re.search(r"against\s+comment", nxt, flags=re.IGNORECASE):
        pairs.append((col, nxt))
        i += 2
    else:
        i += 1

rows = []

for vote_col, comment_col in pairs:
    tmp = df[base_cols + [vote_col, comment_col]].copy()
    tmp = tmp.rename(columns={
        vote_col: "vote_raw",
        comment_col: "against_reason"
    })
    tmp["investor"] = vote_col
    rows.append(tmp)

long_df = pd.concat(rows, ignore_index=True)

# Clean votes
long_df["vote_raw"] = long_df["vote_raw"].astype(str).str.strip()
long_df["vote"] = long_df["vote_raw"].str.upper()

long_df = long_df[long_df["vote"].isin(["AGAINST", "FOR"])]

# Clean reasons
long_df["against_reason"] = (
    long_df["against_reason"]
    .astype(str)
    .replace({"nan": ""})
    .str.strip()
)

long_df.to_csv(OUT_PATH, index=False)

print("Saved:", OUT_PATH)
print("Rows:", len(long_df))
print(long_df.head(5))
