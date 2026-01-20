# judge_investors.py

import csv
import json
import re
from typing import Dict, Any, Optional

import pandas as pd

from config import client, JUDGE_MODEL

FINGERPRINTS_PATH = "investor_fingerprints.json"

# Strict explicit language detector (policy must clearly say it will vote against / oppose)
EXPLICIT_AGAINST_RE = re.compile(
    r"\b(vote\s+against|will\s+vote\s+against|oppose|will\s+oppose|will\s+not\s+support|not\s+support)\b",
    flags=re.IGNORECASE
)

JUDGE_SYSTEM_PROMPT = """
You are an expert stewardship / proxy voting analyst.

You will receive:
1) An investor's voting policy text (focused on executive remuneration).
2) A JSON object describing a company's remuneration facts for the current year.
3) (Optional) An investor behavioural profile derived from their historical AGAINST reasons.
4) OVERRIDE_FLAGS which control whether certain strict overrides are permitted.

Your job is to decide how this investor would vote on the company's
remuneration resolution and briefly explain why.

Return a STRICT JSON object with exactly these fields:
  - vote: "FOR" or "AGAINST"
  - reason: 1–3 sentences explaining which policy rule(s) and fact(s) drove the decision.
  - confidence: a number between 0 and 1 (float).
  - key_violations: a list of short strings describing breaches or concerns
                    relative to the investor's policy (empty list if none).

Be harsh in your votes.

Do not include markdown. Do not include any other fields.
"""


def clean_policy_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return (
        s.replace("â€™", "’")
         .replace("â€œ", "“")
         .replace("â€", "”")
         .replace("â€“", "–")
    )


def compute_pay_for_performance_override_allowed(policy_text: str, fingerprint: Optional[Dict[str, Any]]) -> bool:
    """
    Deterministic gate:
      (A) policy explicitly says it will vote against / oppose in certain cases, OR
      (B) behavioural profile indicates strong pay-for-performance sensitivity.
    """
    if EXPLICIT_AGAINST_RE.search(policy_text or ""):
        return True

    # IMPORTANT: This assumes you added 'pay_for_performance_strong' in your fingerprint builder.
    if fingerprint and fingerprint.get("pay_for_performance_sensitive") is True:
        return True

    return False


def build_judge_user_prompt(
    policy_text: str,
    facts: Dict[str, Any],
    fingerprint: Optional[Dict[str, Any]],
    override_flags: Dict[str, Any]
) -> str:
    fp_str = json.dumps(fingerprint, indent=2) if fingerprint else "null"
    flags_str = json.dumps(override_flags, indent=2)

    return f"""
[INVESTOR_POLICY]
{policy_text}
[/INVESTOR_POLICY]

[INVESTOR_BEHAVIOURAL_PROFILE]
{fp_str}
[/INVESTOR_BEHAVIOURAL_PROFILE]

[OVERRIDE_FLAGS]
{flags_str}
[/OVERRIDE_FLAGS]

[FACTS_JSON]
{json.dumps(facts, indent=2)}
[/FACTS_JSON]

Using ONLY the policy, behavioural profile (if provided), OVERRIDE_FLAGS, and facts above:

- Decide how this investor would vote on the company's remuneration resolution (FOR or AGAINST).
- Base your decision on explicit policy rules and the numeric/boolean fields in the JSON.
- If important data for a rule is missing (null), list it in key_violations as "Missing data: <fieldname>" and reduce confidence.
- In your reason, explicitly reference the JSON field names and values you relied on (e.g., financial_performance.eps_change_pct=-38.46, total_dilution_pct=null).

Return ONLY a JSON object with the fields:
  vote, reason, confidence, key_violations.
""".strip()


def judge_single_investor(
    policy_text: str,
    facts: Dict[str, Any],
    fingerprint: Optional[Dict[str, Any]],
    override_flags: Dict[str, Any]
) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": build_judge_user_prompt(policy_text, facts, fingerprint, override_flags)},
        ],
        temperature=1,
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    vote = str(data.get("vote", "")).upper().strip()
    if vote not in ("FOR", "AGAINST"):
        vote = "FOR"
    data["vote"] = vote

    try:
        data["confidence"] = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        data["confidence"] = 0.5

    key_violations = data.get("key_violations", [])
    if not isinstance(key_violations, list):
        key_violations = [str(key_violations)]
    data["key_violations"] = [str(v) for v in key_violations]

    return data


def judge_all_investors(investor_csv_path: str, facts_json_path: str, output_csv_path: str) -> None:
    investors = pd.read_csv(investor_csv_path)
    investors.columns = [c.strip().replace("\ufeff", "") for c in investors.columns]

    with open(FINGERPRINTS_PATH, "r", encoding="utf-8") as f:
        fingerprints = json.load(f)

    with open(facts_json_path, "r", encoding="utf-8") as f:
        facts = json.load(f)

    fieldnames = ["investor_name", "vote", "confidence", "reason", "key_violations"]

    with open(output_csv_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        out_f.flush()

        for idx, row in investors.iterrows():
            investor_name = row.get("Investor")
            policy_text = clean_policy_text(row.get("RemunerationPolicy", ""))

            if not isinstance(policy_text, str) or not policy_text.strip():
                print(f"[WARN] Empty policy for investor='{investor_name}', skipping.")
                continue

            fp = fingerprints.get(investor_name)

            override_flags = {
                "pay_for_performance_override_allowed": compute_pay_for_performance_override_allowed(policy_text, fp)
            }

            print(f"Judging investor: {investor_name}... override_allowed={override_flags['pay_for_performance_override_allowed']}")

            try:
                verdict = judge_single_investor(policy_text, facts, fp, override_flags)

                out_row = {
                    "investor_name": investor_name,
                    "vote": verdict["vote"],
                    "confidence": verdict["confidence"],
                    "reason": verdict["reason"],
                    "key_violations": "; ".join(verdict.get("key_violations", [])),
                }

                writer.writerow(out_row)
                out_f.flush()

            except Exception as e:
                print(f"[ERROR] Failed on investor='{investor_name}' row={idx}: {e}")
                writer.writerow({
                    "investor_name": investor_name,
                    "vote": "FOR",
                    "confidence": 0.0,
                    "reason": f"ERROR during judgement: {e}",
                    "key_violations": "ERROR",
                })
                out_f.flush()

    print(f"Saved investor-level predictions to {output_csv_path}")
