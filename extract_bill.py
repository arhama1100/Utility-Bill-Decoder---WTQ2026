import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY .env file mein nahi mili.")

client = genai.Client(api_key=api_key)

TRAIN_DIR = Path("train")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

SCHEMA = """
Return exactly one JSON object with these fields:
{
  "provider": null,
  "tariff": null,
  "sanctioned_load_kw": null,
  "bill_month": null,
  "reading_date": null,
  "issue_date": null,
  "due_date": null,
  "previous_reading": null,
  "current_reading": null,
  "units_consumed": null,
  "charges": [],
  "total_charges": null,
  "taxes": [],
  "total_taxes": null,
  "current_bill": null,
  "arrears": null,
  "payable_within_due_date": null,
  "payable_after_due_date": null
}

Rules:
- Use only information visible on the bill.
- Unknown or unreadable values must be null; do not guess.
- Dates must use YYYY-MM-DD, except bill_month uses YYYY-MM.
- Numeric values must be numbers, without currency symbols or commas.
- charges items: {"type": "energy|fixed|fpa|quarterly_adjustment|surcharge|meter_rent|subsidy|other", "amount": number}
- taxes items: {"type": "gst|electricity_duty|income_tax|municipal_tax|other_tax", "amount": number}
- Use negative amounts for credits or subsidies.
- Exclude names, addresses, CNIC, account/reference/consumer numbers and meter numbers.
- Preserve printed amounts; do not recalculate them.
- provider must be KE, LESCO, or IESCO when identifiable; otherwise null.
- Return JSON only, with all required fields present.
"""

# Find all training bill images
images = sorted(
    p for p in TRAIN_DIR.rglob("*")
    if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
)

if not images:
    raise FileNotFoundError(
        "train folder mein JPG/PNG images nahi milin."
    )

print(f"Total images found: {len(images)}")

# Extract information from every training image
for image_path in images:
    print(f"\nProcessing: {image_path.name}")

    try:
        mime_type = (
            "image/png"
            if image_path.suffix.lower() == ".png"
            else "image/jpeg"
        )

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                SCHEMA,
                {
                    "mime_type": mime_type,
                    "data": image_path.read_bytes(),
                },
            ],
            config={"response_mime_type": "application/json"},
        )

        if not response.text:
            raise ValueError("Model ne empty response return kiya.")

        data = json.loads(response.text)

        required_fields = [
            "provider", "tariff", "sanctioned_load_kw",
            "bill_month", "reading_date", "issue_date", "due_date",
            "previous_reading", "current_reading", "units_consumed",
            "charges", "total_charges", "taxes", "total_taxes",
            "current_bill", "arrears", "payable_within_due_date",
            "payable_after_due_date",
        ]

        for field in required_fields:
            if field not in data:
                data[field] = [] if field in ("charges", "taxes") else None

        output_path = OUTPUT_DIR / f"{image_path.stem}.json"
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"SUCCESS: Saved {output_path}")

    except Exception as error:
        print(f"FAILED: {image_path.name}: {error}")

print("\nTraining image processing finished.")
print(f"JSON files saved in: {OUTPUT_DIR.resolve()}")
