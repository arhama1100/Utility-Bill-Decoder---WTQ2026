from google import genai
from dotenv import load_dotenv
import os

load_dotenv()
print("API key loaded:", bool(os.getenv("GEMINI_API_KEY")))

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Hello! I am ready for my hackathon."
)

print(response.text)