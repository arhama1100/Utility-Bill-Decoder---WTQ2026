⚡ Utility Bill Decoder — WTQ 2026

An AI-powered utility bill processing project built for **Women Tech Quest (WTQ) 2026**. The project extracts structured information from electricity bills and supports natural-language question answering using Google Gemini.

Overview

Electricity bills contain important information such as billing amounts, consumption details, meter readings, and due dates. Extracting this information into a structured format can make bill processing and analysis easier.

Utility Bill Decoder aims to automate this process by converting supported bill documents into structured outputs and answering questions about their contents.

✨ Features

- Bill Information Extraction:** Extracts supported fields from electricity bills.
- Structured Output:** Organizes extracted information into CSV and JSON-compatible formats, according to the implemented pipeline.
- AI-Powered Question Answering:** Uses Google Gemini to answer questions about bill content.
- Multiple Bill Providers:** Designed for supported K-Electric (KE/KESC), LESCO, and IESCO bill formats.
- Python-Based Pipeline:** Provides scripts for running extraction and related processing tasks.

🛠️ Tech Stack

- Language: Python
- AI Model/API: Google Gemini API
- Data Formats: CSV and JSON
- Configuration: Environment variables using a `.env` file

## 📁 Project Structure

```text
Utility-Bill-Decoder/
├── extract_bill.py
├── run_train_level1.py
├── test_gemini.py
├── test_kesc0008.py
├── test_level2_kesc0008.py
├── README.md
├── .gitignore
└── source/
    ├── .env.example
    ├── README.md
    ├── config.py
    ├── level1_extractor.py
    ├── level2_qa.py
    ├── main.py
    └── requirements.txt
```

🚀 Getting Started

1. Clone the repository

```bash
git clone https://github.com/arhama1100/Utility-Bill-Decoder---WTQ2026.git
cd Utility-Bill-Decoder---WTQ2026
```

2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

3. Install dependencies

```bash
pip install -r source/requirements.txt
```

4. Configure your API key

Create a `.env` file in the location expected by the application configuration. Use `source/.env.example` as a reference and add your own Google Gemini API key.

Never commit your real API key or `.env` file to GitHub.

5. Run the project

Check `source/README.md` for the project's exact execution instructions and required input paths before running the extraction pipeline.

📊 Output

The pipeline is designed to produce structured bill information and question-answering results in the formats required by the project workflow. Actual output fields depend on the implemented extraction logic and input document.

🔒 Security and Privacy

- Keep API keys and other secrets out of version control.
- Use sample bills with personal account details removed when sharing demonstrations.
- Verify extracted values against the original bill before relying on them.

🎯 Project Context

Developed as part of **Women Tech Quest (WTQ) 2026 — Build Track**.

👩‍💻 Author

Arhama
GitHub: [@arhama1100](https://github.com/arhama1100)

📌 Future Improvements

- Improve extraction accuracy across different bill layouts.
- Add validation for missing or inconsistent fields.
- Expand support for additional utility bill formats.
- Develop a simple user interface for uploading bills and reviewing results.
- Add evaluation metrics and documented examples.

---

*This project is intended for learning, experimentation, and structured document processing. Verify extracted information against the original bill.*
