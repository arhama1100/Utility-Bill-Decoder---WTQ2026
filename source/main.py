import os
import sys
import json
import csv
import argparse
import zipfile
from pathlib import Path

# Add project root and source dir to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from source.level1_extractor import Level1Extractor
from source.level2_qa import Level2QAEngine

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

DEFAULT_SAMPLE_QUESTIONS = [
    ("Q1", "How much of my bill is taxes?"),
    ("Q2", "How many months in my history went above 200 units?"),
    ("Q3", "What is the due date and what is payable within due date?"),
    ("Q4", "What is the cost per unit charged for electricity?"),
    ("Q5", "Are there any late payment surcharges or penalties applied?"),
    ("Q6", "What is my sanctioned load in kW?"),
    ("Q7", "Is there any fuel price adjustment (FPA/FCA) on this bill?"),
    ("Q8", "What was my previous meter reading versus current reading?"),
    ("Q9", "Are there any arrears or previous credit balances on this bill?"),
    ("Q10", "What is the tariff category listed on this bill?"),
    ("Q11", "How many total units were consumed during this billing cycle?"),
    ("Q12", "What is the amount payable after the due date?")
]

def find_bill_images(bills_dir: Path):
    if not bills_dir.exists():
        return []
    return sorted(
        p for p in bills_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
    )

def load_level2_questions(level2_csv_path: Path):
    """Load question template rows from level2.csv if available."""
    if not level2_csv_path.exists():
        return None
    
    questions_by_bill = {}
    with open(level2_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bill_id = row["bill_id"].strip()
            q_id = row["question_id"].strip()
            q_text = row["question"].strip()
            if bill_id not in questions_by_bill:
                questions_by_bill[bill_id] = []
            questions_by_bill[bill_id].append((q_id, q_text))
    return questions_by_bill

def process_all(bills_dir: Path, level2_template_csv: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_out_dir = output_dir / "json"
    json_out_dir.mkdir(parents=True, exist_ok=True)

    images = find_bill_images(bills_dir)
    if not images:
        print(f"Error: No bill images found in {bills_dir}")
        return

    print(f"==================================================")
    print(f"  WTQ Utility Bill Decoder - Pipeline Execution")
    print(f"==================================================")
    print(f"Target Bills Directory: {bills_dir.resolve()}")
    print(f"Total Bill Images Found: {len(images)}")
    print(f"Output Directory:       {output_dir.resolve()}")
    print(f"==================================================\n")

    extractor = Level1Extractor()
    qa_engine = Level2QAEngine()

    level1_results = []
    level1_data_map = {}

    # 1. Process Level 1 Extraction
    print("--- LEVEL 1: Extracting Billing Details ---")
    for img_path in images:
        bill_id = img_path.stem
        print(f"Processing Level 1 for [{bill_id}] ({img_path.name})...")
        try:
            data = extractor.extract_bill(img_path)
            level1_data_map[bill_id] = data
            
            # Save individual JSON
            (json_out_dir / f"{bill_id}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            
            # Compact string for level1.csv
            json_str = json.dumps(data, ensure_ascii=False)
            level1_results.append((bill_id, json_str))
            print(f"  [OK] Level 1 Success: {bill_id}")
        except Exception as e:
            print(f"  [FAIL] Level 1 Failed for {bill_id}: {e}")

    # Write output/level1.csv
    level1_csv_path = output_dir / "level1.csv"
    with open(level1_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["bill_id", "json"])
        for bill_id, json_str in level1_results:
            writer.writerow([bill_id, json_str])
    print(f"\n[+] Wrote {len(level1_results)} rows to {level1_csv_path}\n")

    # 2. Process Level 2 Q&A
    print("--- LEVEL 2: Generating Customer Answers ---")
    template_questions = load_level2_questions(level2_template_csv)
    
    level2_results = []

    for img_path in images:
        bill_id = img_path.stem
        level1_data = level1_data_map.get(bill_id, {})
        
        # Determine questions to answer for this bill
        if template_questions and bill_id in template_questions:
            q_list = template_questions[bill_id]
        else:
            q_list = DEFAULT_SAMPLE_QUESTIONS

        print(f"Processing Level 2 for [{bill_id}] ({len(q_list)} questions)...")
        for q_id, q_text in q_list:
            try:
                answer = qa_engine.answer_question(img_path, level1_data, q_id, q_text)
                level2_results.append((bill_id, q_id, q_text, answer))
                print(f"  [OK] Answered {q_id} for {bill_id}")
            except Exception as e:
                print(f"  [FAIL] Error answering {q_id} for {bill_id}: {e}")
                level2_results.append((bill_id, q_id, q_text, "Information not available on the bill."))

    # Write output/level2.csv
    level2_csv_path = output_dir / "level2.csv"
    with open(level2_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["bill_id", "question_id", "question", "answer"])
        for b_id, q_id, q_text, ans in level2_results:
            writer.writerow([b_id, q_id, q_text, ans])
    print(f"\n[+] Wrote {len(level2_results)} rows to {level2_csv_path}\n")

    print("==================================================")
    print("  Pipeline Completed Successfully!")
    print("==================================================")

def create_submission_zip(output_zip: Path):
    """Package output/, source/, and demo/ into your-submission.zip"""
    print(f"\n[+] Packaging submission zip: {output_zip}")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add output folder
        output_dir = BASE_DIR / "output"
        if output_dir.exists():
            for f in output_dir.glob("*.csv"):
                zipf.write(f, arcname=f"output/{f.name}")

        # Add source folder
        source_dir = BASE_DIR / "source"
        if source_dir.exists():
            for f in source_dir.rglob("*"):
                if f.is_file() and "__pycache__" not in str(f):
                    rel = f.relative_to(BASE_DIR)
                    zipf.write(f, arcname=str(rel))

        # Add demo folder if exists
        demo_dir = BASE_DIR / "demo"
        if demo_dir.exists():
            for f in demo_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(BASE_DIR)
                    zipf.write(f, arcname=str(rel))

    zip_size_mb = output_zip.stat().st_size / (1024 * 1024)
    print(f"[OK] Submission ZIP created: {output_zip} ({zip_size_mb:.2f} MB)")
    if zip_size_mb > 15:
        print("[!] WARNING: Submission ZIP exceeds 15 MB limit!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WTQ Utility Bill Decoder Pipeline")
    parser.add_argument(
        "--bills-dir",
        type=str,
        default=None,
        help="Path to directory containing bill images (default: test/bills if exists else train/bills)"
    )
    parser.add_argument(
        "--template-csv",
        type=str,
        default=None,
        help="Path to level2.csv template file"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to save output level1.csv and level2.csv"
    )
    parser.add_argument(
        "--make-zip",
        action="store_true",
        help="Create submission zip after running pipeline"
    )

    args = parser.parse_args()

    # Determine default paths
    test_bills = BASE_DIR / "test" / "bills"
    train_bills = BASE_DIR / "train" / "bills"
    
    if args.bills_dir:
        bills_dir = Path(args.bills_dir)
    elif test_bills.exists() and any(test_bills.glob("*")):
        bills_dir = test_bills
    else:
        bills_dir = train_bills

    if args.template_csv:
        template_csv = Path(args.template_csv)
    else:
        template_csv = BASE_DIR / "test" / "csv" / "level2.csv"

    output_dir = BASE_DIR / args.output_dir

    process_all(bills_dir, template_csv, output_dir)

    if args.make_zip or True:
        zip_path = BASE_DIR / "submission.zip"
        create_submission_zip(zip_path)
