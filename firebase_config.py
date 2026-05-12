import firebase_admin
import os
from firebase_admin import credentials
from firebase_admin import firestore

# Try to use environment variable first, then fall back to file
firebase_credentials = os.environ.get('FIREBASE_CREDENTIALS')
if firebase_credentials:
    # Use environment variable (JSON string)
    import json
    cred_dict = json.loads(firebase_credentials)
    cred = credentials.Certificate(cred_dict)
else:
    # Fall back to file for local development
    cred = credentials.Certificate("serviceAccountKey.json")

firebase_admin.initialize_app(cred)

db = firestore.client()