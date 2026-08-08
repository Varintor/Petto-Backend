# Manual Gemini smoke checks

These scripts call the real Gemini API and are intentionally excluded from
pytest discovery. Configure `GEMINI_API_KEY` locally, then run a script
explicitly from the repository root, for example:

```powershell
.\.venv\Scripts\python.exe scripts\manual\gemini_smoke.py
```

They must never print, commit, or embed any part of the API key.
