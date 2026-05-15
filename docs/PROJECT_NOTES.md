# Budget Calendar Notes

## Storage

Local development should use `scratch/run_server.py`. That launcher sets `REQUIRE_FIREBASE=1`, so the app fails loudly if Firebase is unavailable instead of saving new data into `budget.db` by accident.

For hosted deployment, set `FIREBASE_CREDENTIALS` to the service-account JSON string. Keep `serviceAccountKey.json` local only.

## Python Environment

The old `.venv` and `venv` launchers in this workspace point to missing Python installs. Current local runs use the Codex bundled Python plus `.local_packages`, which is ignored by git.

For a clean setup later, rebuild one fresh virtual environment and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Desktop App

`main.py` is the older CustomTkinter desktop version. The active web app entrypoint is `app.py`; keep `main.py` only if you still want the desktop build.
