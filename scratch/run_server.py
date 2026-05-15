from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = ROOT / ".local_packages"
SITE_PACKAGES = ROOT / "venv" / "Lib" / "site-packages"

sys.path.insert(0, str(ROOT))
if SITE_PACKAGES.exists():
    sys.path.insert(0, str(SITE_PACKAGES))
if LOCAL_PACKAGES.exists():
    sys.path.insert(0, str(LOCAL_PACKAGES))


if __name__ == "__main__":
    os.environ.setdefault("REQUIRE_FIREBASE", "1")
    from app import app, db

    print(f"Using {db.backend_name()} storage backend.")
    app.run(host="127.0.0.1", port=5000, debug=False)
