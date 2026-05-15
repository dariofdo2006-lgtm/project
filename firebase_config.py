import firebase_admin
import os
from firebase_admin import credentials
from firebase_admin import firestore

SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"

# Try to use environment variable first, then fall back to file.
firebase_credentials = os.environ.get('FIREBASE_CREDENTIALS')
if firebase_credentials:
    import json
    cred_dict = json.loads(firebase_credentials)
    cred = credentials.Certificate(cred_dict)
elif os.path.exists(SERVICE_ACCOUNT_PATH):
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
else:
    raise RuntimeError(
        "Firebase credentials not configured. Set FIREBASE_CREDENTIALS "
        f"or add {SERVICE_ACCOUNT_PATH} for local development."
    )

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
