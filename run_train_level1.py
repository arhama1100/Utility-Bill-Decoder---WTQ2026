import os
import json
import csv
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

TRAIN_DIR = Path("train/bills")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
JSON_DIR = OUTPUT_DIR / "json"
JSON_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

SYSTEM_PROMPT = """You are an expert utility bill parser for Pakistani electricity bills (K-Electric / KE, LESCO, IESCO).
Extract all billing details accurately according to the exact JSON template and rules below.

JSON Schema to return (must include all key names even if null):
{
  "provider": "KE | LESCO | IESCO",
  "tariff": "string",
  "sanctioned_load_kw": number,
  "bill_month": "YYYY-MM",
  "reading_date": "YYYY-MM-DD",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "previous_reading": number,
  "current_reading": number,
  "units_consumed": number,
  "charges": [
    {
      "type": "energy | fixed | fpa | quarterly_adjustment | surcharge | meter_rent | subsidy | other",
      "amount": number
    }
  ],
  "total_charges": number,
  "taxes": [
    {
      "type": "gst | electricity_duty | income_tax | municipal_tax | other_tax",
      "amount": number
    }
  ],
  "total_taxes": number,
  "current_bill": number,
  "arrears": number,
  "payable_within_due_date": number,
  "payable_after_due_date": number
}

Field extraction guidelines:
1. provider: Must be "KE" (for K-Electric/KESC bills), "LESCO", or "IESCO". (Note: KESC/K-Electric bills MUST use "KE").
2. tariff: Tariff code exactly as printed, e.g. "A1-R" or "A-1a(01)".
3. sanctioned_load_kw: Sanctioned load in kW as a number (e.g. 3).
4. bill_month: YYYY-MM format (e.g., "2026-04" for Apr 2026 / Bill Month: Apr-26).
5. reading_date, issue_date, due_date: YYYY-MM-DD format (e.g., "2026-04-03", "2026-04-07", "2026-04-21").
6. previous_reading, current_reading, units_consumed: Printed meter readings and current month units billed.
7. charges: List of individual line items in the charges section. Skip zero amounts and blank lines.
   Types allowed:
   - "energy": Cost of units used (e.g. Variable Upto ... Units, Cost of Electricity, Energy Charges). Return separate entries for each slab line.
   - "fixed": Fixed charges.
   - "fpa": Fuel price adjustment / FCA / FPA.
   - "quarterly_adjustment": Quarterly tariff adjustment (QTA, Uniform Quarterly Adjustment).
   - "surcharge": Surcharges (Additional Surcharge PHL, F.C Surcharge, etc.).
   - "meter_rent": Meter rent or service rent.
   - "subsidy": Government subsidy / relief lines. Record as NEGATIVE number (e.g., -100).
   - "other": Any other charge line.
8. total_charges: Printed electricity charges subtotal (number), or null if not printed.
9. taxes: List of line items in taxes / government section.
   Types allowed:
   - "gst": Sales tax / GST / GST on FPA.
   - "electricity_duty": Electricity duty (ED).
   - "income_tax": Income tax.
   - "municipal_tax": Municipal/local charges under taxes, such as KE MUCT (KMC).
   - "other_tax": Any other tax line (extra tax, further tax, TV fee).
   Note: If only a combined tax subtotal is printed without individual breakdown, return [] for taxes and put that total in total_taxes.
10. total_taxes: Printed tax subtotal (number), or null if not printed.
11. current_bill: Printed amount for current month's bill (excluding arrears).
12. arrears: Previous dues carried forward (number). If CR / credit, record as negative number (e.g. -0.53).
13. payable_within_due_date: Total amount payable by due date (number).
14. payable_after_due_date: Amount payable after due date. If multiple late-payment amounts are shown (e.g. 5% vs 10%), use the HIGHEST value.

Rules:
- Amounts must be pure numbers in PKR (remove "Rs.", commas, currency symbols).
- Credits/subsidies must be negative numbers.
- Unreadable or missing fields must be null (or [] for charges/taxes if none). Do NOT guess.
- Do NOT recalculate or round printed amounts; extract as printed.
- Exclude all personal identifiers (names, addresses, CNIC, account/ref/consumer/meter numbers).
"""

REQUIRED_FIELDS = [
    "provider", "tariff", "sanctioned_load_kw", "bill_month",
    "reading_date", "issue_date", "due_date", "previous_reading",
    "current_reading", "units_consumed", "charges", "total_charges",
    "taxes", "total_taxes", "current_bill", "arrears",
    "payable_within_due_date", "payable_after_due_date"
]

images = sorted(
    p for p in TRAIN_DIR.rglob("*")
    if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
)

print(f"Found {len(images)} images in {TRAIN_DIR}")

level1_rows = []

for image_path in images:
    bill_id = image_path.stem
    print(f"\nProcessing {bill_id} ({image_path.name})...")
    
    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)
    
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[SYSTEM_PROMPT, part],
            config={"response_mime_type": "application/json"}
        )
        
        data = json.loads(response.text)
        
        # Enforce field structure and key ordering
        ordered_data = {}
        for key in REQUIRED_FIELDS:
            if key in ("charges", "taxes"):
                ordered_data[key] = data.get(key, []) if isinstance(data.get(key), list) else []
            else:
                ordered_data[key] = data.get(key, None)
                
        # Save JSON file
        json_file = JSON_DIR / f"{bill_id}.json"
        json_file.write_text(json.dumps(ordered_data, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Compact single-line json string for CSV cell
        json_compact = json.dumps(ordered_data, ensure_ascii=False)
        level1_rows.append((bill_id, json_compact))
        
        print(f"SUCCESS: {bill_id} extracted.")
    except Exception as e:
        print(f"ERROR processing {bill_id}: {e}")

# Write level1.csv
csv_path = OUTPUT_DIR / "level1.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["bill_id", "json"])
    for bill_id, json_str in level1_rows:
        writer.writerow([bill_id, json_str])

print(f"\nWrote {len(level1_rows)} rows to {csv_path.resolve()}")
