import json
import pandas as pd
from typing import Dict, Any
from config import client, JUDGE_MODEL


JUDGE_SYSTEM_PROMPT = """
You are an expert stewardship analyst.

You will receive:
1) An investor's voting policy text (focused on remuneration / executive pay).
2) A JSON object describing a company's remuneration facts for the current year.

Your job is to decide how the investor would vote on the remuneration resolution
(FOR or AGAINST) and briefly explain why.

Requirements:
- Base your decision ONLY on the investor policy and the provided facts.
- If the policy says, for example, "vote AGAINST if dilution exceeds 10%", then:
  - Compare the numeric values correctly (e.g. 12.5 > 10).
- If necessary information is missing from the facts, choose the vote that the policy suggests
  in such cases, and explain the uncertainty.
- Use a strict JSON response with keys: vote, reason, confidence.
  - vote: "FOR" or "AGAINST"
  - reason: short human-readable explanation (1-2 sentences)
  - confidence: number between 0 and 1 representing how confident you are
"""


def build_judge_user_prompt(policy_text: str, facts: Dict[str, Any]) -> str:
    return f"""
[INVESTOR_POLICY]
{policy_text}
[/INVESTOR_POLICY]

[REMUNERATION_FACTS_JSON]
{json.dumps(facts, indent=2)}
[/REMUNERATION_FACTS_JSON]

Decide the investor's vote (FOR or AGAINST) on the company's remuneration resolution,
using ONLY the information above.

Return ONLY a JSON object with fields: vote, reason, confidence.
"""


def judge_single_investor(policy_text: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": build_judge_user_prompt(policy_text, facts)},
        ],
        temperature=0.1,
    )

    content = response.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(f"Model returned invalid JSON: {content[:500]}")

    # Small hygiene / normalization
    data["vote"] = data.get("vote", "").upper().strip()
    if data["vote"] not in ["FOR", "AGAINST"]:
        data["vote"] = "FOR"  # default, or raise

    data["confidence"] = float(data.get("confidence", 0.5))

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
