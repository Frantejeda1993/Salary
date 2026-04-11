import streamlit as st
from google.api_core import exceptions as gcloud_exceptions
from google.cloud import firestore
from google.oauth2 import service_account

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


@st.cache_data(ttl=120, show_spinner=False)
def _cached_get_all(collection_name: str) -> list:
    try:
        collection = get_db().collection(collection_name)
        docs = collection.stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except gcloud_exceptions.ResourceExhausted:
        st.error(
            "Firestore quota/rate limit reached while loading data. "
            "Please wait a moment and reload the app."
        )
        return []


@st.cache_data(ttl=120, show_spinner=False)
def _cached_get_by_field(collection_name: str, field: str, operator: str, value) -> list:
    try:
        collection = get_db().collection(collection_name)
        docs = collection.where(filter=firestore.FieldFilter(field, operator, value)).stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except gcloud_exceptions.ResourceExhausted:
        st.error(
            "Firestore quota/rate limit reached while loading filtered data. "
            "Please wait a moment and reload the app."
        )
        return []


@st.cache_data(ttl=120, show_spinner=False)
def _cached_get_by_fields(collection_name: str, filters: tuple) -> list:
    """
    filters format:
        (
            (field_name, operator, value),
            ...
        )
    """
    try:
        query = get_db().collection(collection_name)
        for field, operator, value in filters:
            query = query.where(filter=firestore.FieldFilter(field, operator, value))
        docs = query.stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except gcloud_exceptions.ResourceExhausted:
        st.error(
            "Firestore quota/rate limit reached while loading multi-filter data. "
            "Please wait a moment and reload the app."
        )
        return []


@st.cache_data(ttl=120, show_spinner=False)
def _cached_get_by_id(collection_name: str, doc_id: str) -> dict:
    try:
        doc = get_db().collection(collection_name).document(doc_id).get()
        if doc.exists:
            return {"id": doc.id, **doc.to_dict()}
        return None
    except gcloud_exceptions.ResourceExhausted:
        st.error(
            "Firestore quota/rate limit reached while loading an item. "
            "Please wait a moment and reload the app."
        )
        return None


def _clear_firestore_caches():
    _cached_get_all.clear()
    _cached_get_by_field.clear()
    _cached_get_by_fields.clear()
    _cached_get_by_id.clear()


def clear_firestore_read_caches():
    """Public and safe cache invalidation for Firestore read operations."""
    _clear_firestore_caches()

class FirestoreService:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.db = get_db()
        self.collection = self.db.collection(self.collection_name)

    def get_all(self) -> list:
        return _cached_get_all(self.collection_name)

    def get_by_field(self, field: str, operator: str, value) -> list:
        return _cached_get_by_field(self.collection_name, field, operator, value)

    def get_by_fields(self, filters: list[tuple]) -> list:
        # tuple(filters) keeps cache key hashable and stable for st.cache_data
        return _cached_get_by_fields(self.collection_name, tuple(filters))

    def add(self, data: dict) -> str:
        # Ensure we don't save 'id' field to the document body itself
        if 'id' in data:
            del data['id']
        _, doc_ref = self.collection.add(data)
        _clear_firestore_caches()
        return doc_ref.id

    def update(self, doc_id: str, data: dict):
        if 'id' in data:
            del data['id']
        self.collection.document(doc_id).update(data)
        _clear_firestore_caches()

    def delete(self, doc_id: str):
        self.collection.document(doc_id).delete()
        _clear_firestore_caches()

    def get_by_id(self, doc_id: str) -> dict:
        return _cached_get_by_id(self.collection_name, doc_id)
