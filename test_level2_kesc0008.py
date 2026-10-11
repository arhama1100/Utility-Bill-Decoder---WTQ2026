import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

image_path = Path("train/bills/KESC_0008.png")
level1_json = json.loads(Path("test_kesc0008.py").read_text()) if False else {
  "provider": "KE",
  "tariff": "A1-R",
  "sanctioned_load_kw": 3,
  "bill_month": "2026-04",
  "reading_date": "2026-04-03",
  "issue_date": "2026-04-07",
  "due_date": "2026-04-21",
  "previous_reading": 8819,
  "current_reading": 8970,
  "units_consumed": 151,
  "charges": [
    {"type": "fixed", "amount": 900},
    {"type": "energy", "amount": 1054},
    {"type": "energy", "amount": 663.51},
    {"type": "quarterly_adjustment", "amount": 52.91},
    {"type": "fpa", "amount": 125.27},
    {"type": "surcharge", "amount": 64.93}
  ],
  "total_charges": 2860.62,
  "taxes": [
    {"type": "electricity_duty", "amount": 29.41},
    {"type": "gst", "amount": 520.21},
    {"type": "municipal_tax", "amount": 20}
  ],
  "total_taxes": 569.62,
  "current_bill": 3430.24,
  "arrears": -0.53,
  "payable_within_due_date": 3430,
  "payable_after_due_date": 3716
}

questions = [
    ("Q1", "How much of my bill is taxes?"),
    ("Q2", "How many months in my history went above 200 units?")
]

SYSTEM_PROMPT = f"""You are an AI assistant answering customer questions about an electricity bill in plain English.
You are given the bill image and the extracted billing details JSON.

Extracted Billing Details:
{json.dumps(level1_json, indent=2)}

Rules for answering:
1. Get numbers exactly right. State exact numbers, percentages, sums, counts, or differences grounded strictly in the bill.
2. Ground each answer strictly in the bill image and JSON. Do NOT use outside tariff rates or outside knowledge. If information is not on the bill, state clearly that it is unavailable.
3. Label estimates clearly. Explain how the estimate was calculated.
4. If a question is ambiguous, explain the interpretation used or answer both interpretations.
5. Exclude personal identifiers (names, addresses, CNIC, account/consumer numbers, meter numbers).
6. Always answer in clear, plain English, even if parts of the bill are in Urdu.
7. Be concise, direct, clear, and complete.
"""

part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png")

for q_id, q_text in questions:
    user_prompt = f"Question ({q_id}): {q_text}\nProvide a direct, complete, plain English answer based ONLY on the bill."
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[SYSTEM_PROMPT, part, user_prompt]
    )
    print(f"[{q_id}] Question: {q_text}")
    print(f"Answer: {response.text.strip()}\n")
