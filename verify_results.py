import csv
import json
import re
from pathlib import Path

BASE_DIR = Path(".")
level1_path = BASE_DIR / "output" / "level1.csv"
level2_path = BASE_DIR / "output" / "level2.csv"
test_level1_template = BASE_DIR / "test" / "csv" / "level1.csv"
test_level2_template = BASE_DIR / "test" / "csv" / "level2.csv"

ALLOWED_PROVIDERS = {"KE", "LESCO", "IESCO"}
ALLOWED_CHARGE_TYPES = {
    "energy", "fixed", "fpa", "quarterly_adjustment",
    "surcharge", "meter_rent", "subsidy", "other"
}
ALLOWED_TAX_TYPES = {
    "gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax"
}
REQUIRED_KEYS = [
    "provider", "tariff", "sanctioned_load_kw", "bill_month",
    "reading_date", "issue_date", "due_date", "previous_reading",
    "current_reading", "units_consumed", "charges", "total_charges",
    "taxes", "total_taxes", "current_bill", "arrears",
    "payable_within_due_date", "payable_after_due_date"
]

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_REGEX = re.compile(r"^\d{4}-\d{2}$")

def test_level1():
    print("=== Testing output/level1.csv ===")
    assert level1_path.exists(), "output/level1.csv does not exist"
    
    with open(level1_path, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert len(reader) == 11, f"Expected 11 lines (header + 10 bills), found {len(reader)}"
    header = reader[0]
    assert header == ["bill_id", "json"], f"Header mismatch: {header}"

    # Check order against template
    with open(test_level1_template, "r", encoding="utf-8") as f:
        template_reader = list(csv.reader(f))
    expected_bill_ids = [row[0] for row in template_reader[1:]]

    actual_bill_ids = [row[0] for row in reader[1:]]
    assert actual_bill_ids == expected_bill_ids, f"Bill IDs or order mismatch: {actual_bill_ids} vs {expected_bill_ids}"

    issues = []
    for row_idx, row in enumerate(reader[1:], start=2):
        bill_id, json_str = row[0], row[1]
        try:
            data = json.loads(json_str)
        except Exception as e:
            issues.append(f"Row {row_idx} ({bill_id}): JSON decode error: {e}")
            continue

        # Check all keys
        for key in REQUIRED_KEYS:
            if key not in data:
                issues.append(f"Row {row_idx} ({bill_id}): Missing required key '{key}'")

        # Provider check
        provider = data.get("provider")
        if provider not in ALLOWED_PROVIDERS:
            issues.append(f"Row {row_idx} ({bill_id}): Invalid provider '{provider}'")
        if bill_id.startswith("KESC") and provider != "KE":
            issues.append(f"Row {row_idx} ({bill_id}): Provider must be 'KE' for KESC bills, got '{provider}'")

        # Dates check
        for d_key in ["reading_date", "issue_date", "due_date"]:
            val = data.get(d_key)
            if val is not None and not DATE_REGEX.match(str(val)):
                issues.append(f"Row {row_idx} ({bill_id}): {d_key}='{val}' does not match YYYY-MM-DD")
        
        b_month = data.get("bill_month")
        if b_month is not None and not MONTH_REGEX.match(str(b_month)):
            issues.append(f"Row {row_idx} ({bill_id}): bill_month='{b_month}' does not match YYYY-MM")

        # Numeric fields check
        num_fields = [
            "sanctioned_load_kw", "previous_reading", "current_reading",
            "units_consumed", "total_charges", "total_taxes",
            "current_bill", "arrears", "payable_within_due_date", "payable_after_due_date"
        ]
        for nf in num_fields:
            val = data.get(nf)
            if val is not None and not isinstance(val, (int, float)):
                issues.append(f"Row {row_idx} ({bill_id}): {nf}='{val}' is not a number or null")

        # Charges check
        charges = data.get("charges")
        if not isinstance(charges, list):
            issues.append(f"Row {row_idx} ({bill_id}): charges is not a list")
        else:
            for c_idx, c in enumerate(charges):
                if not isinstance(c, dict):
                    issues.append(f"Row {row_idx} ({bill_id}): charge[{c_idx}] is not a dict")
                    continue
                c_type = c.get("type")
                c_amount = c.get("amount")
                if c_type not in ALLOWED_CHARGE_TYPES:
                    issues.append(f"Row {row_idx} ({bill_id}): invalid charge type '{c_type}'")
                if c_amount is not None and not isinstance(c_amount, (int, float)):
                    issues.append(f"Row {row_idx} ({bill_id}): charge amount '{c_amount}' is not a number")
                if c_amount is None:
                    issues.append(f"Row {row_idx} ({bill_id}): charge[{c_idx}] has null amount: {c}")

        # Taxes check
        taxes = data.get("taxes")
        if not isinstance(taxes, list):
            issues.append(f"Row {row_idx} ({bill_id}): taxes is not a list")
        else:
            for t_idx, t in enumerate(taxes):
                if not isinstance(t, dict):
                    issues.append(f"Row {row_idx} ({bill_id}): tax[{t_idx}] is not a dict")
                    continue
                t_type = t.get("type")
                t_amount = t.get("amount")
                if t_type not in ALLOWED_TAX_TYPES:
                    issues.append(f"Row {row_idx} ({bill_id}): invalid tax type '{t_type}'")
                if t_amount is not None and not isinstance(t_amount, (int, float)):
                    issues.append(f"Row {row_idx} ({bill_id}): tax amount '{t_amount}' is not a number")
                if t_amount is None:
                    issues.append(f"Row {row_idx} ({bill_id}): tax[{t_idx}] has null amount: {t}")

    print(f"Level 1 validation complete. Total issues found: {len(issues)}")
    for iss in issues:
        print("  -", iss)
    return len(issues) == 0

def test_level2():
    print("\n=== Testing output/level2.csv ===")
    assert level2_path.exists(), "output/level2.csv does not exist"

    with open(level2_path, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert len(reader) == 121, f"Expected 121 rows (header + 120 Q&As), found {len(reader)}"
    header = reader[0]
    assert header == ["bill_id", "question_id", "question", "answer"], f"Header mismatch: {header}"

    with open(test_level2_template, "r", encoding="utf-8") as f:
        template_reader = list(csv.reader(f))

    assert len(template_reader) == 121, f"Template row count mismatch: {len(template_reader)}"
    
    issues = []
    empty_answers = 0
    short_answers = 0

    for i in range(1, 121):
        actual_row = reader[i]
        tmpl_row = template_reader[i]

        # Verify bill_id, question_id, question match template exactly
        if actual_row[0] != tmpl_row[0]:
            issues.append(f"Row {i+1}: bill_id mismatch '{actual_row[0]}' vs template '{tmpl_row[0]}'")
        if actual_row[1] != tmpl_row[1]:
            issues.append(f"Row {i+1}: question_id mismatch '{actual_row[1]}' vs template '{tmpl_row[1]}'")
        if actual_row[2] != tmpl_row[2]:
            issues.append(f"Row {i+1}: question text mismatch")

        answer = actual_row[3].strip()
        if not answer:
            empty_answers += 1
            issues.append(f"Row {i+1} ({actual_row[0]}, {actual_row[1]}): Empty answer!")
        elif len(answer) < 10:
            short_answers += 1
            issues.append(f"Row {i+1} ({actual_row[0]}, {actual_row[1]}): Suspiciously short answer: '{answer}'")

    print(f"Level 2 validation complete. Total issues found: {len(issues)}")
    for iss in issues[:10]:
        print("  -", iss)
    if len(issues) > 10:
        print(f"  ... and {len(issues) - 10} more.")
    return len(issues) == 0

if __name__ == "__main__":
    l1_ok = test_level1()
    l2_ok = test_level2()
    print("\nOVERALL TEST RESULT:", "PASS" if (l1_ok and l2_ok) else "FAIL")
