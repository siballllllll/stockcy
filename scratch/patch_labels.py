import sys

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_label = '"axisLabel": {"color": "#888", "fontSize": 14, "interval": _label_interval}'
new_label = '"axisLabel": {"color": "#888", "fontSize": 12, "interval": "auto", "hideOverlap": True}'

if old_label in content:
    new_content = content.replace(old_label, new_label)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated app.py labels")
else:
    print("Label snippet not found")
