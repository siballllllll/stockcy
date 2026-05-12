import streamlit as st, google.genai as genai
client = genai.Client(api_key=st.secrets['gemini']['api_key'])
for m in ['gemini-2.5-flash', 'gemini-3.1-flash-lite', 'gemini-3.0-flash']:
    try:
        client.models.generate_content(model=m, contents='hi')
        print(f"{m} OK")
    except Exception as e:
        print(f"{m} FAIL: {e}")
