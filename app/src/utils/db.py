import os
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

def get_client():
    """
    Initializes and returns a MongoDB client.
    Uses Streamlit's cache_resource to prevent re-creating the client on each re-run.
    """
    load_dotenv()
    mongo_user = os.getenv("MONGO_USER")
    mongo_pass = os.getenv("MONGO_PASS")

    if not mongo_user or not mongo_pass:
        st.error("❌ Missing MongoDB credentials in .env file")
        st.stop()

    uri = f"mongodb+srv://{mongo_user}:{mongo_pass}@cluster0.l7fdbmf.mongodb.net"
    return MongoClient(uri)

def get_db():
    """
    Returns a handle to the 'mit261' database.
    """
    client = get_client()
    return client["mit261"]
