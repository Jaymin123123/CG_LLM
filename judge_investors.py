import json
import pandas as pd
from typing import Dict, Any
from config import client, JUDGE_MODEL


JUDGE_SYSTEM_PROMPT = """
You are an expert stewardship / proxy voting analyst.

You will receive:
1) An investor's voting policy text (focused on executive remuneration).
2) A JSON object describing a company's remuneration facts for the current year.

Your job is to decide how this investor would vote on the company's remuneration
resolution and briefly explain why.

IMPORTANT RULES:

- Base your decision ONLY on:
  (a) the investor policy text, and
  (b) the remuneration facts JSON.
  Do NOT use market practice, general governance views, or outside knowledge.

- Treat the investor policy as the source of rules. For example:
    "Vote AGAINST if dilution exceeds 10%"
    "Vote AGAINST if CEO pay grows faster than the wider workforce"
    "Expect at least 20% of variable pay linked to ESG metrics"

- Use the structured fields in the facts JSON whenever relevant, for example:
    ceo_target_bonus_pct_of_salary
    ceo_max_bonus_pct_of_salary
    ceo_ltip_max_pct_of_salary
    ceo_salary_increase_pct
    workforce_salary_increase_pct
    total_dilution_pct
    dilution_policy_limit_pct
    sti_total_esg_weight_pct
    ltip_total_esg_weight_pct
    esg_metrics_incentives_present
    clawback_provision
    malus_provision

- Always do correct numeric comparisons, e.g.:
    12.5 > 10
    0 is not greater than 5
    If a threshold is "at least 20%", then 20 is acceptable but 19 is not.

- If a policy rule refers to information that is missing (null) in the facts JSON,
  you may still make a judgement using the remaining information, but you must
  acknowledge the missing data in your explanation.

- If the policy clearly indicates an AGAINST in the current situation, choose "AGAINST".
  Otherwise choose "FOR". Do not invent an ABSTAIN option.

Return a STRICT JSON object with the following fields:

- vote: "FOR" or "AGAINST"
- reason: a short human-readable explanation (1–3 sentences) mentioning
          the key policy rule(s) and fact(s) that drove the decision.
- confidence: a number between 0 and 1 indicating your confidence in the decision.
- key_violations: a list of short strings describing any breaches or concerns
                  relative to the investor's policy (empty list if none).

Do not include any other fields. Do not include markdown.
"""



def build_judge_user_prompt(policy_text: str, facts: Dict[str, Any]) -> str:
    return f"""
[INVESTOR_POLICY]
{policy_text}
[/INVESTOR_POLICY]

[REMUNERATION_FACTS_JSON]
{json.dumps(facts, indent=2)}
[/REMUNERATION_FACTS_JSON]

Using ONLY the policy and facts above:

- Decide how this investor would vote on the company's remuneration resolution (FOR or AGAINST).
- Base your decision on explicit policy rules and the numeric/boolean fields in the JSON.
- If important data for a rule is missing (null), note this in your explanation.

Return ONLY a JSON object with the fields: vote, reason, confidence, key_violations.
"""


def judge_single_investor(policy_text: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": build_judge_user_prompt(policy_text, facts)},
        ],
        temperature=1,
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    # Normalise
    vote = str(data.get("vote", "")).upper().strip()
    if vote not in ["FOR", "AGAINST"]:
        vote = "FOR"
    data["vote"] = vote

    try:
        data["confidence"] = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        data["confidence"] = 0.5

    # Ensure key_violations is a list
    kv = data.get("key_violations", [])
    if not isinstance(kv, list):
        kv = [str(kv)]
    data["key_violations"] = [str(x) for x in kv]

    return data



def judge_all_investors(
    investor_csv_path: str,
    facts_json_path: str,
    output_csv_path: str
):
    investors = pd.read_csv(investor_csv_path)
    with open(facts_json_path, "r", encoding="utf-8") as f:
        facts = json.load(f)

    results = []
    for _, row in investors.iterrows():
        investor_id = row.get("investor_id")
        investor_name = row.get("investor_name")
        policy_text = row.get("policy_text", "")

        if not isinstance(policy_text, str) or not policy_text.strip():
            print(f"[WARN] Empty policy for investor_id={investor_id}, skipping.")
            continue

        print(f"Judging investor {investor_id} - {investor_name}...")

        out = judge_single_investor(policy_text, facts)
        out["investor_id"] = investor_id
        out["investor_name"] = investor_name

        results.append(out)

    df_results = pd.DataFrame(results)
    df_results.to_csv(output_csv_path, index=False)
    print(f"Saved investor-level judgments to {output_csv_path}")


if __name__ == "__main__":
    # Example usage:
    # python judge_investors.py investor_policies.csv facts.json investor_votes.csv
    import sys

    investor_csv_path = sys.argv[1]
    facts_json_path = sys.argv[2]
    output_csv_path = sys.argv[3]

    judge_all_investors(investor_csv_path, facts_json_path, output_csv_path)
