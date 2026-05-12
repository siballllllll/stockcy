import json
import streamlit as st
from google import genai

try:
    api_key = st.secrets["gemini"]["api_key"]
    client = genai.Client(api_key=api_key)
    
    available_models = []
    for m in client.models.list():
        available_models.append(m.name)
    print("Available Models:", json.dumps(available_models, indent=2))
except Exception as e:
    print("Error:", e)
