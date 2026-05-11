from firebase_config import db

doc_ref = db.collection("test").document("example")

doc_ref.set({
    "name": "Dario",
    "status": "working"
})

print("Firebase is working!")