import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from source.config import LEVEL2_SYSTEM_PROMPT, GEMINI_API_KEY, MODEL_NAME

logger = logging.getLogger(__name__)

def call_with_retry(client: genai.Client, model_name: str, contents: list, max_retries: int = 6):
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(
                model=model_name,
                contents=contents
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "Quota" in err_str:
                delay = 5.0 * (1.5 ** attempt)
                print(f"    [Rate Limit 429] Waiting {delay:.1f}s before retry ({attempt+1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise e
    # Final attempt
    return client.models.generate_content(model=model_name, contents=contents)

class Level2QAEngine:
    def __init__(self, api_key: Optional[str] = None, model_name: str = MODEL_NAME):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("API Key is required for Gemini model.")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name

    def answer_question(
        self,
        image_path: Path,
        level1_data: Dict[str, Any],
        question_id: str,
        question_text: str,
        pace: bool = True,
    ) -> str:
        """Answer a customer question for a given bill image and its extracted details."""
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)

        user_prompt = f"""Bill Details JSON:
{json.dumps(level1_data, indent=2)}

Question ({question_id}): {question_text}

Answer the question directly, accurately, and completely in plain English using ONLY the bill details and image.
Follow all rules: verify all numbers/counts/percentages precisely, label any estimates, state missing info if unavailable, exclude personal details."""

        response = call_with_retry(
            client=self.client,
            model_name=self.model_name,
            contents=[LEVEL2_SYSTEM_PROMPT, part, user_prompt]
        )

        answer = response.text.strip() if response.text else "Information not available on the bill."
        answer_clean = answer.replace("\n\n", " ").replace("\n", " ").strip()
        
        # Batch jobs pause between calls to stay within rate limits.
        if pace:
            time.sleep(3.5)

        return answer_clean
