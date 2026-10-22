import os
import sys
import json
import csv
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import tempfile

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from source.config import GEMINI_API_KEY, MODEL_NAME, REQUIRED_LEVEL1_FIELDS
from source.level1_extractor import Level1Extractor
from source.level2_qa import Level2QAEngine
from source.main import process_all, create_submission_zip

app = FastAPI(title="WTQ Utility Bill Decoder", version="1.0.0")

# Middleware to normalize Vercel serverless paths
@app.middleware("http")
async def vercel_path_rewrite_middleware(request: Request, call_next):
    matched = request.headers.get("x-matched-path")
    if matched:
        request.scope["path"] = matched
    elif request.scope.get("path") in ("/api/index.py", "/api/index", "/api"):
        request.scope["path"] = "/"
    return await call_next(request)

# Setup directory paths with serverless writable fallback
def get_writable_dir(sub_name: str) -> Path:
    target = BASE_DIR / sub_name
    try:
        target.mkdir(parents=True, exist_ok=True)
        test_file = target / ".write_test"
        test_file.touch()
        test_file.unlink()
        return target
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "wtq_2026" / sub_name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = get_writable_dir("uploads")
OUTPUT_DIR = get_writable_dir("output")
JSON_DIR = get_writable_dir("output/json")

# Instantiate engine instances
extractor = Level1Extractor()
qa_engine = Level2QAEngine()

class QuestionRequest(BaseModel):
    bill_id: str
    image_rel_path: str
    question: str
    question_id: Optional[str] = "CUSTOM"

@app.get("/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
@app.get("/api/index", response_class=HTMLResponse)
@app.get("/api/index.py", response_class=HTMLResponse)
async def serve_index():
    candidates = [
        STATIC_DIR / "index.html",
        BASE_DIR / "public" / "index.html",
        BASE_DIR / "source" / "static" / "index.html",
    ]
    for p in candidates:
        if p.exists():
            return HTMLResponse(content=p.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Index template not found.")

@app.get("/api/bills")
async def list_available_bills():
    """List sample bills available in test/bills and train/bills."""
    bills = []
    
    test_dir = BASE_DIR / "test" / "bills"
    if test_dir.exists():
        for p in sorted(test_dir.glob("*")):
            if p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                bills.append({
                    "id": p.stem,
                    "filename": p.name,
                    "folder": "test",
                    "path": f"test/bills/{p.name}"
                })

    train_dir = BASE_DIR / "train" / "bills"
    if train_dir.exists():
        for p in sorted(train_dir.glob("*")):
            if p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                bills.append({
                    "id": p.stem,
                    "filename": p.name,
                    "folder": "train",
                    "path": f"train/bills/{p.name}"
                })

    return {"bills": bills}

@app.get("/api/image")
async def get_bill_image(rel_path: str):
    """Serve bill image given relative path safely."""
    safe_path = (BASE_DIR / rel_path).resolve()
    # Check that resolved path is inside BASE_DIR
    if not str(safe_path).startswith(str(BASE_DIR.resolve())) or not safe_path.exists():
        raise HTTPException(status_code=404, detail="Image not found.")
    media_type = "image/png" if safe_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(safe_path, media_type=media_type)

@app.get("/api/extracted-json/{bill_id}")
async def get_preextracted_json(bill_id: str):
    """Retrieve pre-extracted Level 1 JSON if available."""
    json_path = JSON_DIR / f"{bill_id}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return {"found": True, "data": data}
        except Exception:
            pass
    return {"found": False, "data": None}

@app.post("/api/extract")
async def extract_bill(
    rel_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """Extract Level 1 details from an existing bill path or newly uploaded file."""
    if file and file.filename:
        # Save uploaded file
        dest_path = UPLOAD_DIR / file.filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_path = dest_path
        bill_id = dest_path.stem
        img_rel = f"uploads/{file.filename}"
    elif rel_path:
        image_path = BASE_DIR / rel_path
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Specified bill image not found.")
        bill_id = image_path.stem
        img_rel = rel_path
    else:
        raise HTTPException(status_code=400, detail="Must provide either an uploaded file or rel_path.")

    try:
        data = extractor.extract_bill(image_path)
        # Save to json folder
        (JSON_DIR / f"{bill_id}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return {
            "success": True,
            "bill_id": bill_id,
            "image_rel_path": img_rel,
            "data": data
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.post("/api/ask")
async def ask_question(req: QuestionRequest):
    """Answer customer question using grounded Level 2 engine."""
    req_path = Path(req.image_rel_path)
    if req_path.is_absolute() and req_path.exists():
        image_path = req_path
    elif (UPLOAD_DIR / req.image_rel_path).exists():
        image_path = UPLOAD_DIR / req.image_rel_path
    elif (BASE_DIR / req.image_rel_path).exists():
        image_path = BASE_DIR / req.image_rel_path
    else:
        raise HTTPException(status_code=404, detail="Bill image not found.")

    # Load Level 1 data
    json_path = JSON_DIR / f"{req.bill_id}.json"
    level1_data = {}
    if json_path.exists():
        try:
            level1_data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        answer = qa_engine.answer_question(
            image_path=image_path,
            level1_data=level1_data,
            question_id=req.question_id or "Q",
            question_text=req.question
        )
        return {
            "success": True,
            "bill_id": req.bill_id,
            "question": req.question,
            "answer": answer
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/api/status")
async def get_status():
    """Get project status, row counts, and submission zip availability."""
    l1_file = OUTPUT_DIR / "level1.csv"
    l2_file = OUTPUT_DIR / "level2.csv"
    zip_file = BASE_DIR / "submission.zip"

    l1_rows = 0
    if l1_file.exists():
        with open(l1_file, "r", encoding="utf-8") as f:
            l1_rows = max(0, len(list(csv.reader(f))) - 1)

    l2_rows = 0
    if l2_file.exists():
        with open(l2_file, "r", encoding="utf-8") as f:
            l2_rows = max(0, len(list(csv.reader(f))) - 1)

    zip_info = None
    if zip_file.exists():
        size_mb = zip_file.stat().st_size / (1024 * 1024)
        zip_info = {
            "exists": True,
            "size_mb": round(size_mb, 2),
            "valid_size": size_mb <= 15.0
        }

    return {
        "level1_rows": l1_rows,
        "level2_rows": l2_rows,
        "submission_zip": zip_info
    }

@app.get("/api/download/submission")
async def download_submission():
    """Download the generated submission.zip file."""
    zip_file = BASE_DIR / "submission.zip"
    if not zip_file.exists():
        create_submission_zip(zip_file)
    return FileResponse(zip_file, media_type="application/zip", filename="your-submission.zip")

if __name__ == "__main__":
    import uvicorn
    print("Starting WTQ Utility Bill Decoder UI on http://127.0.0.1:8000 ...")
    uvicorn.run("source.app:app", host="127.0.0.1", port=8000, reload=False)
