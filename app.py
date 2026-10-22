"""
Launcher for WTQ Utility Bill Decoder Web UI.
Run with:
    python app.py
Open in browser:
    http://127.0.0.1:8000
"""

import uvicorn

if __name__ == "__main__":
    print("\n==================================================")
    print("  WTQ Utility Bill Decoder - Web Application")
    print("==================================================")
    print("  Local URL: http://127.0.0.1:8000")
    print("  Press Ctrl+C to stop the server.")
    print("==================================================\n")
    uvicorn.run("source.app:app", host="127.0.0.1", port=8000, reload=False)
