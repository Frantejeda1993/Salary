import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json

@st.cache_resource
def get_db():
    if "firebase" in st.secrets:
        key_dict = dict(st.secrets["firebase"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        db = firestore.Client(credentials=creds, project=key_dict["project_id"])
    else:
        # Fallback to local default credentials if not running on Streamlit Cloud with secrets
        db = firestore.Client()
    return db

class FirestoreService:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.db = get_db()
        self.collection = self.db.collection(self.collection_name)

    def get_all(self) -> list:
        docs = self.collection.stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]

    def get_by_field(self, field: str, operator: str, value) -> list:
        docs = self.collection.where(filter=firestore.FieldFilter(field, operator, value)).stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]

    def add(self, data: dict) -> str:
        # Ensure we don't save 'id' field to the document body itself
        if 'id' in data:
            del data['id']
        _, doc_ref = self.collection.add(data)
        return doc_ref.id

    def update(self, doc_id: str, data: dict):
        if 'id' in data:
            del data['id']
        self.collection.document(doc_id).update(data)

    def delete(self, doc_id: str):
        self.collection.document(doc_id).delete()

    def get_by_id(self, doc_id: str) -> dict:
        doc = self.collection.document(doc_id).get()
        if doc.exists:
            return {"id": doc.id, **doc.to_dict()}
        return None
