import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from source.config import LEVEL1_SYSTEM_PROMPT, REQUIRED_LEVEL1_FIELDS, GEMINI_API_KEY, MODEL_NAME

logger = logging.getLogger(__name__)

def call_with_retry(client: genai.Client, model_name: str, contents: list, config: Optional[dict] = None, max_retries: int = 5):
    for attempt in range(max_retries):
        try:
            kwargs = {"config": config} if config else {}
            return client.models.generate_content(
                model=model_name,
                contents=contents,
                **kwargs
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "Quota" in err_str:
                delay = 4.5 * (1.5 ** attempt)
                print(f"    [Rate Limit 429] Waiting {delay:.1f}s before retry ({attempt+1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise e
    # Final attempt
    kwargs = {"config": config} if config else {}
    return client.models.generate_content(model=model_name, contents=contents, **kwargs)

class Level1Extractor:
    def __init__(self, api_key: Optional[str] = None, model_name: str = MODEL_NAME):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("API Key is required for Gemini model.")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name

    def extract_bill(self, image_path: Path) -> Dict[str, Any]:
        """Extract Level 1 JSON schema from a bill image path."""
        if not image_path.exists():
            raise FileNotFoundError(f"Bill image not found: {image_path}")

        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)

        response = call_with_retry(
            client=self.client,
            model_name=self.model_name,
            contents=[LEVEL1_SYSTEM_PROMPT, part],
            config={"response_mime_type": "application/json"}
        )

        if not response.text:
            raise ValueError(f"Model returned empty response for {image_path.name}")

        data = json.loads(response.text)

        # Ensure all required fields exist in exact template order
        clean_data = {}
        for key in REQUIRED_LEVEL1_FIELDS:
            if key == "charges":
                raw_charges = data.get("charges", [])
                clean_charges = []
                if isinstance(raw_charges, list):
                    for c in raw_charges:
                        if isinstance(c, dict) and "amount" in c and "type" in c:
                            amt = c["amount"]
                            if amt is not None and isinstance(amt, (int, float)) and amt != 0:
                                clean_charges.append({"type": str(c["type"]), "amount": amt})
                clean_data["charges"] = clean_charges
            elif key == "taxes":
                raw_taxes = data.get("taxes", [])
                clean_taxes = []
                if isinstance(raw_taxes, list):
                    for t in raw_taxes:
                        if isinstance(t, dict) and "amount" in t and "type" in t:
                            amt = t["amount"]
                            if amt is not None and isinstance(amt, (int, float)) and amt != 0:
                                clean_taxes.append({"type": str(t["type"]), "amount": amt})
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

        return clean_data

