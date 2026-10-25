import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient

from source.app import app, error_payload
from source.errors import AppError, classify_exception, redact_secrets


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ErrorHelperTests(unittest.TestCase):
    def test_redact_api_key_values(self):
        raw = "api_key=AIzaSyDummyKeyValue1234567890 and Bearer abc.def"
        redacted = redact_secrets(raw)
        self.assertNotIn("AIza", redacted)
        self.assertNotIn("abc.def", redacted)
        self.assertIn("[redacted]", redacted)

    def test_missing_config_classification(self):
        code, message, status = classify_exception(ValueError("API Key is required"), gemini_configured=False)
        self.assertEqual(code, "missing_config")
        self.assertEqual(status, 503)
        self.assertIn("GEMINI_API_KEY", message)

    def test_timeout_classification(self):
        code, message, status = classify_exception(TimeoutError("deadline exceeded"), gemini_configured=True)
        self.assertEqual(code, "timeout")
        self.assertEqual(status, 504)


class ExtractApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_reports_missing_key_without_exposing_secret(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["gemini_configured"])
        self.assertNotIn("api_key", json.dumps(body).lower())

    def test_extract_rejects_missing_file(self):
        response = self.client.post("/api/extract")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "invalid_request")
        self.assertTrue(body["error"])

    def test_extract_rejects_unsupported_pdf(self):
        response = self.client.post(
            "/api/extract",
            files={"file": ("bill.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "unsupported_file")
        self.assertIn("PNG", body["error"])

    def test_error_payload_includes_error_and_code(self):
        payload = error_payload("unsupported_file", "Use a PNG or JPG bill image.", 400)
        body = json.loads(payload.body.decode())
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "unsupported_file")
        self.assertIn("PNG", body["error"])

    def test_extract_succeeds_with_mock_model(self):
        sample = {
            "provider": "KE",
            "tariff": "A1-R",
            "sanctioned_load_kw": 3,
            "bill_month": "2026-04",
            "reading_date": "2026-04-03",
            "issue_date": "2026-04-07",
            "due_date": "2026-04-21",
            "previous_reading": 100,
            "current_reading": 150,
            "units_consumed": 50,
            "charges": [{"type": "energy", "amount": 1000}],
            "total_charges": 1000,
            "taxes": [{"type": "gst", "amount": 170}],
            "total_taxes": 170,
            "current_bill": 1170,
            "arrears": 0,
            "payable_within_due_date": 1170,
            "payable_after_due_date": 1287,
        }

        class DummyExtractor:
            def extract_bill(self, image_path):
                self.path = image_path
                return sample

        dummy = DummyExtractor()
        with patch("source.app.get_extractor", return_value=dummy):
            response = self.client.post(
                "/api/extract",
                files={"file": ("ke-bill.png", io.BytesIO(PNG_BYTES), "image/png")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["provider"], "KE")
        self.assertEqual(body["bill_id"], "ke-bill")

    def test_root_multipart_post_is_routed_to_extract(self):
        class DummyExtractor:
            def extract_bill(self, image_path):
                return {"provider": "IESCO", "charges": [], "taxes": []}

        with patch("source.app.get_extractor", return_value=DummyExtractor()):
            response = self.client.post(
                "/",
                files={"file": ("iesco.png", io.BytesIO(PNG_BYTES), "image/png")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["success"])

    def test_vercel_function_path_post_is_routed_to_extract(self):
        sample = {"provider": "LESCO", "charges": [], "taxes": []}

        class DummyExtractor:
            def extract_bill(self, image_path):
                return sample

        with patch("source.app.get_extractor", return_value=DummyExtractor()):
            response = self.client.post(
                "/api/index.py",
                files={"file": ("lesco.png", io.BytesIO(PNG_BYTES), "image/png")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["success"])

    def test_missing_gemini_config_is_explicit(self):
        def boom():
            raise AppError(
                "missing_config",
                "Bill extraction is not configured on the server. Set GEMINI_API_KEY in the Vercel project environment variables.",
                503,
            )

        with patch("source.app.get_extractor", side_effect=boom):
            response = self.client.post(
                "/api/extract",
                files={"file": ("ke-bill.png", io.BytesIO(PNG_BYTES), "image/png")},
            )
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["code"], "missing_config")
        self.assertIn("GEMINI_API_KEY", body["error"])


if __name__ == "__main__":
    unittest.main()
