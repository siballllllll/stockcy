import re

target_file = 'app.py'
with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Increase base font size in CSS
content = content.replace('font-size: 21px;', 'font-size: 24px;')

# 2. Scale rem-based font sizes in CSS and style attributes
def scale_rem(match):
    prefix = match.group(1)
    val = float(match.group(2))
    suffix = match.group(3)
    
    if val < 1.0:
        new_val = val * 1.30 # 30% increase for small fonts
    else:
        new_val = val * 1.15 # 15% increase for larger fonts
    
    return f"{prefix}{new_val:.2f}rem{suffix}"

# Match patterns like: font-size: 0.82rem !important; or style='font-size:0.85rem'
content = re.sub(r'(font-size\s*:\s*)([0-9.]+)(rem)', scale_rem, content)

# 3. Scale ECharts fontSize in Python dictionaries
def scale_echarts_font(match):
    val = int(match.group(2))
    new_val = int(val * 1.15)
    return f'{match.group(1)}{new_val}'

content = re.sub(r'("fontSize":\s*)([0-9]+)', scale_echarts_font, content)

# 4. Specific fix for some hardcoded small fonts in f-strings
content = content.replace('font-size:0.6rem', 'font-size:0.85rem')
content = content.replace('font-size:0.55rem', 'font-size:0.75rem')
content = content.replace('font-size:0.65rem', 'font-size:0.85rem')
content = content.replace('font-size:0.62rem', 'font-size:0.82rem')
content = content.replace('font-size:0.68rem', 'font-size:0.88rem')
content = content.replace('font-size:0.7rem', 'font-size:0.95rem')
content = content.replace('font-size:0.72rem', 'font-size:0.95rem')
content = content.replace('font-size:0.75rem', 'font-size:1.0rem')
content = content.replace('font-size:0.78rem', 'font-size:1.0rem')
content = content.replace('font-size:0.8rem', 'font-size:1.05rem')
content = content.replace('font-size:0.82rem', 'font-size:1.1rem')
content = content.replace('font-size:0.85rem', 'font-size:1.1rem')

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("Font sizes scaled up successfully.")
