import csv
import json
from pathlib import Path
from source.config import REQUIRED_LEVEL1_FIELDS

ALLOWED_CHARGE_TYPES = {
    "energy", "fixed", "fpa", "quarterly_adjustment",
    "surcharge", "meter_rent", "subsidy", "other"
}
ALLOWED_TAX_TYPES = {
    "gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax"
}

level1_csv = Path("output/level1.csv")
with open(level1_csv, "r", encoding="utf-8") as f:
    rows = list(csv.reader(f))

updated_rows = [rows[0]]

for row in rows[1:]:
    bill_id = row[0]
    data = json.loads(row[1])

    clean_data = {}
    for key in REQUIRED_LEVEL1_FIELDS:
        if key == "charges":
            clean_charges = []
            for c in data.get("charges", []):
                amt = c.get("amount")
                if amt is not None and isinstance(amt, (int, float)) and amt != 0 and c.get("type") in ALLOWED_CHARGE_TYPES:
                    clean_charges.append({"type": c["type"], "amount": amt})
            clean_data["charges"] = clean_charges
        elif key == "taxes":
            clean_taxes = []
            for t in data.get("taxes", []):
                amt = t.get("amount")
                if amt is not None and isinstance(amt, (int, float)) and amt != 0 and t.get("type") in ALLOWED_TAX_TYPES:
                    clean_taxes.append({"type": t["type"], "amount": amt})
            clean_data["taxes"] = clean_taxes
        elif key == "provider":
            prov = data.get("provider")
            if prov:
                prov_str = str(prov).upper()
                if "KESC" in prov_str or "KE" in prov_str or "ELECTRIC" in prov_str:
                    clean_data["provider"] = "KE"
                elif "LESCO" in prov_str:
                    clean_data["provider"] = "LESCO"
                elif "IESCO" in prov_str:
                    clean_data["provider"] = "IESCO"
                else:
                    clean_data["provider"] = prov
            else:
                clean_data["provider"] = None
        else:
            clean_data[key] = data.get(key, None)

    # Save to json file
    json_path = Path(f"output/json/{bill_id}.json")
    json_path.write_text(json.dumps(clean_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Add to updated rows
    compact_json = json.dumps(clean_data, ensure_ascii=False)
    updated_rows.append([bill_id, compact_json])

with open(level1_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerows(updated_rows)

print("Updated output/level1.csv and output/json/ successfully.")
