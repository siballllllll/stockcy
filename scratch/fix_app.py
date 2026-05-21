import codecs

with codecs.open('app.py', 'r', 'utf-8') as f:
    content = f.read()

insert_code = """
    # 다이얼로그 네이티브 닫힘 감지:
    if st.session_state.get("_dialog_open", False):
        if not st.session_state.pop("_dialog_body_ran", False):
            st.session_state["_dialog_open"] = False

"""

new_content = content.replace('if __name__ == "__main__":', insert_code + 'if __name__ == "__main__":')

with codecs.open('app.py', 'w', 'utf-8') as f:
    f.write(new_content)
print("done")
