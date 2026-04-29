from google import genai
import streamlit as st
client = genai.Client(api_key=st.secrets["gemini"]["api_key"])
for m in client.models.list():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
