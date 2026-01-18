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

CRITICAL RULES:

- Base your decision ONLY on:
  (a) the investor policy text,
  (b) the facts JSON provided,
  (c) the optional investor behavioural profile provided, and
  (d) OVERRIDE_FLAGS.
  Do NOT use general market practice, your own preferences, or outside knowledge.

- Investor behavioural profile usage:
  You may use the behavioural profile as a PRIOR for what this investor tends to vote AGAINST,
  especially when the written policy is vague or incomplete. However, do NOT override an explicit
  policy rule with the profile. If there is a conflict, the explicit policy rule takes precedence.

- You MUST NOT claim a feature exists unless it is explicitly present in the facts JSON.
  Treat null as "unknown / not evidenced". Do not assume typical governance features exist.

- Treat the investor policy as a set of rules or principles. Examples of rules:
    • "Vote AGAINST if dilution exceeds 10%."
    • "Vote AGAINST where CEO bonus opportunity exceeds 100% of salary."
    • "Expect at least 20% of variable pay to be linked to ESG metrics."
    • "Expect meaningful clawback and malus provisions."
    • "Remuneration should reward success / align with performance."

- Use the structured JSON fields whenever relevant, for example:
    • ceo_target_bonus_pct_of_salary
    • ceo_max_bonus_pct_of_salary
    • ceo_ltip_max_pct_of_salary
    • ceo_salary_increase_pct
    • workforce_salary_increase_pct
    • total_dilution_pct
    • ltip_dilution_pct
    • stip_dilution_pct
    • dilution_policy_limit_pct
    • sti_total_esg_weight_pct
    • ltip_total_esg_weight_pct
    • esg_metrics_incentives_present
    • clawback_provision
    • malus_provision
    • post_cessation_holding_years
    • shareholding_requirement_ceo

- The facts JSON may include a "financial_performance" object (e.g., eps_change_pct,
  profit_attributable_change_pct). You may use this ONLY if:
    (a) the investor policy indicates pay-for-performance principles OR
    (b) the behavioural profile suggests the investor is pay-for-performance sensitive.

- Note: ceo_ltip_max_pct_of_salary represents maximum opportunity (not necessarily paid outcome).
  Do not vote AGAINST solely on high opportunity unless policy/profile and financial deterioration support it.

- Pay-for-performance override (STRICT + GATED):
  You may apply this override ONLY if OVERRIDE_FLAGS.pay_for_performance_override_allowed is true.

  If the override is allowed AND
     (financial_performance.eps_change_pct <= -10 OR financial_performance.profit_attributable_change_pct <= -10) AND
     (ceo_ltip_max_pct_of_salary >= 500 OR ceo_max_bonus_pct_of_salary >= 150),
  then vote AGAINST unless the facts explicitly show reduced awards or strong justification.

- Always do correct numeric comparisons. For example:
    • 12.5 > 10
    • 10 is NOT greater than 10, but it meets an "at least 10%" threshold.
    • If a rule is "no more than 2x salary" and the fact is 3x, that breaches the rule.

- If important data required by a policy rule is missing (null in the JSON),
  you MUST:
    (a) add a key_violations entry like "Missing data: <fieldname>"
    (b) reduce confidence (generally <= 0.45)
  You may still vote FOR or AGAINST depending on what the policy implies about insufficient disclosure,
  but you must not treat missing data as evidence of compliance.

- If the policy clearly implies an AGAINST given the available facts, vote "AGAINST".
  Otherwise vote "FOR", but do not overstate certainty when key fields are missing.

Return a STRICT JSON object with exactly these fields:
  - vote: "FOR" or "AGAINST"
  - reason: 1–3 sentences explaining which policy rule(s) and fact(s) drove the decision.
  - confidence: a number between 0 and 1 (float).
  - key_violations: a list of short strings describing breaches or concerns
                    relative to the investor's policy (empty list if none).

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
    if fingerprint and fingerprint.get("pay_for_performance_strong") is True:
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
        temperature=0.1,
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
