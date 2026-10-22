import sys
from pathlib import Path

# Add project root to sys.path so source module can be resolved in Vercel serverless environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from source.app import app

# Vercel entrypoint
app = app
