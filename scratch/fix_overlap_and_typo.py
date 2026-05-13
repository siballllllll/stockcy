import os

target_file = 'app.py'
with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix the double 'rem' typo
content = content.replace('remrem', 'rem')

# 2. Add anti-ghosting CSS to inject_custom_css
anti_ghosting_css = """
        /* ── 렉(Overlap) 방지: 리렌더링 중 이전 화면 희미하게 처리 ── */
        [data-stale="true"] {
            opacity: 0.25 !important;
            filter: grayscale(1) blur(1px) !important;
            transition: opacity 0.1s ease-in-out !important;
        }
"""

if 'inject_custom_css():' in content:
    # Find the first <style> tag inside inject_custom_css
    content = content.replace('<style>', '<style>' + anti_ghosting_css, 1)

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed rem typos and added anti-ghosting CSS.")
