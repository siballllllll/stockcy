import sys

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_snippet = """                    "itemStyle": {
                        "color": "#ff4b4b", "color0": "#2b7cff",
                        "borderColor": "#ff4b4b", "borderColor0": "#2b7cff"
                    }"""

new_snippet = """                    "itemStyle": {
                        "color": "#ff4b4b", "color0": "#2b7cff",
                        "borderColor": "#ff4b4b", "borderColor0": "#2b7cff"
                    },
                    "markArea": {
                        "silent": True,
                        "data": _mark_areas
                    }"""

if old_snippet in content:
    new_content = content.replace(old_snippet, new_snippet, 1) # Only first one (US chart)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated app.py")
else:
    print("Snippet not found")
