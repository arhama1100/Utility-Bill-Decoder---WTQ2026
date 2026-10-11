# WTQ Build Track - Utility Bill Decoder

AI-powered assistant that parses Pakistani electricity bills (K-Electric / KE, LESCO, IESCO), extracts structured billing details (Level 1), and answers customer questions in plain English (Level 2).

---

## 1. Environment & Prerequisites
- **Runtime**: Python 3.11 or later (Tested on Python 3.14 / 3.11)
- **API Key**: Google AI Studio API Key (Free tier using `gemini-3.5-flash-lite`)

---

## 2. Installation & Setup

1. **Clone / Extract Project**:
   ```bash
   cd source
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` in the root project folder:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your `GEMINI_API_KEY`:
   ```env
   MODEL_PROVIDER=google
   MODEL_NAME=gemini-3.5-flash-lite
   GEMINI_API_KEY=your_actual_gemini_api_key
   ```

---

## 3. How to Run the Project

### Command to Process Bills and Generate Both CSV Files
Run the following command from the project root:
```bash
python source/main.py
```

By default, `source/main.py` automatically checks for test bills in `test/bills`. If present, it reads those; otherwise it defaults to processing `train/bills`.

### Custom Arguments
You can also specify custom directories:
```bash
python source/main.py --bills-dir test/bills --template-csv test/csv/level2.csv --output-dir output
```

### Generated Output Files
- `output/level1.csv`: Contains 1 row per test bill (`bill_id,json`).
- `output/level2.csv`: Contains 120 rows (10 test bills x 12 questions) (`bill_id,question_id,question,answer`).
- `output/json/<bill_id>.json`: Individual pretty-printed JSON files for inspection.
- `submission.zip`: Automatically generated zip package ready for submission.

---

## 4. AI Usage Statement

In compliance with section 7.4 of the WTQ Build Track Participant Guide, here is the full list of AI tools, models, and services used:

- **AI Models & Providers**:
  - `gemini-3.5-flash-lite` (Google AI Studio / `google-genai` SDK) - Used for Level 1 visual bill extraction and Level 2 grounded Q&A answering.
- **APIs & Cloud Services**:
  - Google Gemini API (`google-genai` Python SDK v2.29.0)
- **AI Coding Tools & Assistants**:
  - Antigravity AI Pair Programmer (Google DeepMind) - Used for code structure design, prompt engineering, verification script creation, and documentation.
- **Other AI / Invoice Services**:
  - none (no prohibited receipt/invoice OCR APIs or Azure services were used; local Gemini multimodal processing only).
