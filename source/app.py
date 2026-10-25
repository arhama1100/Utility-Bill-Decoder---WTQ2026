import os
import sys
import json
import csv
import shutil
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

import tempfile

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from source.config import GEMINI_API_KEY, MODEL_NAME
from source.errors import AppError, classify_exception, redact_secrets
from source.level1_extractor import Level1Extractor
from source.level2_qa import Level2QAEngine
from source.main import create_submission_zip

logger = logging.getLogger(__name__)

app = FastAPI(title="WTQ Utility Bill Decoder", version="1.0.0")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg"}
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
FUNCTION_PATHS = {"/api/index.py", "/api/index"}
IS_SERVERLESS = bool(os.getenv("VERCEL"))

_extractor = None
_qa_engine = None


def error_payload(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message, "code": code},
    )


def get_extractor() -> Level1Extractor:
    global _extractor
    if not GEMINI_API_KEY:
        raise AppError(
            "missing_config",
            "Bill extraction is not configured on the server. Set GEMINI_API_KEY in the Vercel project environment variables.",
            503,
        )
    if _extractor is None:
        _extractor = Level1Extractor()
    return _extractor


def get_qa_engine() -> Level2QAEngine:
    global _qa_engine
    if not GEMINI_API_KEY:
        raise AppError(
            "missing_config",
            "Question answering is not configured on the server. Set GEMINI_API_KEY in the Vercel project environment variables.",
            503,
        )
    if _qa_engine is None:
        _qa_engine = Level2QAEngine()
    return _qa_engine


def _recover_request_path(request: Request) -> str:
    current = request.scope.get("path") or "/"
    query_path = request.query_params.get("__vt_path")
    if query_path and query_path.startswith("/"):
        return query_path.split("?")[0]

    invoke_path = (request.headers.get("x-invoke-path") or "").split("?")[0]
    if invoke_path.startswith("/api/") and invoke_path not in FUNCTION_PATHS and not invoke_path.endswith(".py"):
        return invoke_path

    # Keep already-correct FastAPI routes.
    if current.startswith("/api/") and current not in FUNCTION_PATHS and not current.endswith(".py"):
        return current
    if current not in FUNCTION_PATHS | {"/", "/api"} and not current.endswith(".py"):
        return current

    for header in ("x-forwarded-uri", "x-original-uri", "x-vercel-original-path"):
        value = request.headers.get(header)
        if value:
            path = value.split("?")[0]
            if path.startswith("/") and path not in FUNCTION_PATHS and not path.endswith(".py"):
                return path

    matched = request.headers.get("x-matched-path") or ""
    if (
        matched.startswith("/")
        and matched not in FUNCTION_PATHS
        and "(" not in matched
        and not matched.endswith(".py")
    ):
        return matched

    method = request.method.upper()
    content_type = (request.headers.get("content-type") or "").lower()
    if method == "POST" and ("multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type):
        return "/api/extract"
    if method == "POST" and "application/json" in content_type:
        return "/api/ask"
    if method in ("GET", "HEAD"):
        if current.startswith("/api/") and current not in FUNCTION_PATHS:
            return current
        return current if current == "/" else current
    return current


@app.middleware("http")
async def vercel_path_rewrite_middleware(request: Request, call_next):
    original = request.scope.get("path") or "/"
    recovered = _recover_request_path(request)
    if recovered != original:
        request.scope["path"] = recovered

    if request.query_params.get("__vt_path"):
        remaining = [(k, v) for k, v in request.query_params.multi_items() if k != "__vt_path"]
        request.scope["query_string"] = urlencode(remaining).encode()

    return await call_next(request)


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


class QuestionRequest(BaseModel):
    bill_id: str
    image_rel_path: str
    question: str
    question_id: Optional[str] = "CUSTOM"


def validate_upload(file: UploadFile, payload: bytes) -> None:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if not filename:
        raise AppError("unsupported_file", "The uploaded file is missing a name.", 400)

    if suffix not in ALLOWED_IMAGE_EXTENSIONS and content_type not in ALLOWED_IMAGE_MIMES:
        raise AppError(
            "unsupported_file",
            "Unsupported file type. Upload a PNG, JPG, or JPEG electricity bill image (PDF is not supported).",
            400,
        )

    if suffix and suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise AppError(
            "unsupported_file",
            "Unsupported file type. Upload a PNG, JPG, or JPEG electricity bill image (PDF is not supported).",
            400,
        )

    if not payload:
        raise AppError("unsupported_file", "The uploaded file is empty.", 400)

    if len(payload) > MAX_UPLOAD_BYTES:
        raise AppError(
            "file_too_large",
            "The bill image is too large. Please upload a PNG or JPG smaller than 4 MB.",
            413,
        )


def resolve_existing_image(rel_path: str) -> Path:
    safe_name = Path(rel_path).name
    candidates = [
        UPLOAD_DIR / safe_name,
        UPLOAD_DIR / rel_path,
        BASE_DIR / rel_path,
        Path(tempfile.gettempdir()) / "wtq_2026" / "uploads" / safe_name,
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    raise AppError(
        "not_found",
        "The bill image could not be found on the server. Please upload the file again.",
        404,
    )


def fail_from_exception(exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_payload("invalid_request", detail, exc.status_code)

    code, message, status = classify_exception(exc, gemini_configured=bool(GEMINI_API_KEY))
    logger.warning("extract_or_ask_failed code=%s status=%s", code, status)
    return error_payload(code, message, status)


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


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "gemini_configured": bool(GEMINI_API_KEY),
        "model_configured": bool(MODEL_NAME),
        "max_upload_mb": round(MAX_UPLOAD_BYTES / (1024 * 1024), 1),
        "allowed_types": sorted(ALLOWED_IMAGE_EXTENSIONS),
        "serverless": IS_SERVERLESS,
    }


@app.get("/api/bills")
async def list_available_bills():
    """List sample bills available in test/bills and train/bills."""
    bills = []

    test_dir = BASE_DIR / "test" / "bills"
    if test_dir.exists():
        for p in sorted(test_dir.glob("*")):
            if p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
                bills.append({
                    "id": p.stem,
                    "filename": p.name,
                    "folder": "test",
                    "path": f"test/bills/{p.name}"
                })

    train_dir = BASE_DIR / "train" / "bills"
    if train_dir.exists():
        for p in sorted(train_dir.glob("*")):
            if p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
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
@app.post("/extract")
@app.post("/api/extract.py")
async def extract_bill(
    rel_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """Extract Level 1 details from an existing bill path or newly uploaded file."""
    try:
        if file and file.filename:
            filename = Path(file.filename).name
            payload = await file.read()
            validate_upload(file, payload)
            dest_path = UPLOAD_DIR / filename
            dest_path.write_bytes(payload)
            image_path = dest_path
            bill_id = dest_path.stem
            img_rel = f"uploads/{filename}"
        elif rel_path:
            image_path = resolve_existing_image(rel_path)
            bill_id = image_path.stem
            img_rel = rel_path
        else:
            raise AppError(
                "invalid_request",
                "Upload a PNG or JPG bill image, or provide an existing bill path.",
                400,
            )

        data = get_extractor().extract_bill(image_path)
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
        return fail_from_exception(e)


@app.post("/api/ask")
@app.post("/ask")
@app.post("/api/ask.py")
async def ask_question(req: QuestionRequest):
    """Answer customer question using grounded Level 2 engine."""
    try:
        req_path = Path(req.image_rel_path)
        if req_path.is_absolute() and req_path.exists():
            image_path = req_path
        else:
            image_path = resolve_existing_image(req.image_rel_path)

        json_path = JSON_DIR / f"{req.bill_id}.json"
        level1_data = {}
        if json_path.exists():
            try:
                level1_data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        answer = get_qa_engine().answer_question(
            image_path=image_path,
            level1_data=level1_data,
            question_id=req.question_id or "Q",
            question_text=req.question,
            pace=not IS_SERVERLESS,
        )
        return {
            "success": True,
            "bill_id": req.bill_id,
            "question": req.question,
            "answer": answer
        }
    except Exception as e:
        return fail_from_exception(e)


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
        "submission_zip": zip_info,
        "gemini_configured": bool(GEMINI_API_KEY),
    }


@app.get("/api/download/submission")
async def download_submission():
    """Download the generated submission.zip file."""
    zip_file = BASE_DIR / "submission.zip"
    if not zip_file.exists():
        create_submission_zip(zip_file)
    return FileResponse(zip_file, media_type="application/zip", filename="your-submission.zip")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    path = request.url.path
    if path.endswith("/extract") or path.endswith("/extract.py"):
        return error_payload(
            "invalid_request",
            "Upload a PNG or JPG bill image, or provide an existing bill path.",
            400,
        )
    return error_payload("invalid_request", "The request was missing required fields.", 400)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    redacted = redact_secrets(str(exc))
    logger.warning("unhandled_error path=%s type=%s", request.url.path, type(exc).__name__)
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_payload("invalid_request", detail, exc.status_code)
    code, message, status = classify_exception(exc, gemini_configured=bool(GEMINI_API_KEY))
    if not message:
        message = "An unexpected server error occurred while processing the bill."
    if redacted and code == "api_failure":
        message = message
    return error_payload(code, message, status)


if __name__ == "__main__":
    import uvicorn
    print("Starting WTQ Utility Bill Decoder UI on http://127.0.0.1:8000 ...")
    uvicorn.run("source.app:app", host="127.0.0.1", port=8000, reload=False)
