import csv
import json

def audit():
    with open("output/level1.csv", "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    for row in reader[1:]:
        bill_id = row[0]
        d = json.loads(row[1])
        c_sum = sum(c["amount"] for c in d["charges"] if c.get("amount") is not None)
        t_sum = sum(t["amount"] for t in d["taxes"] if t.get("amount") is not None)
        print(f"=== {bill_id} ===")
        print(f"  Charges Count: {len(d['charges'])}, Sum: {c_sum:.2f}, Stated total_charges: {d.get('total_charges')}")
        print(f"  Taxes Count: {len(d['taxes'])}, Sum: {t_sum:.2f}, Stated total_taxes: {d.get('total_taxes')}")
        print(f"  Current Bill: {d.get('current_bill')}, Arrears: {d.get('arrears')}, Payable: {d.get('payable_within_due_date')}")

if __name__ == "__main__":
    audit()
