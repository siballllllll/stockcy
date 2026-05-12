import os

target_file = 'app.py'
with open(target_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
removed_count = 0
for line in lines:
    # 1. Remove local imports that cause UnboundLocalError
    if 'from data_kr import' in line and ('get_us_ticker_map' in line or 'get_kr_code_to_name_map' in line):
        removed_count += 1
        continue
    
    # 2. Fix assignments that used the local import names
    l_strip = line.strip()
    if '_tmp_us_map = _tmp_tm()' in line:
        new_lines.append(line.replace('_tmp_tm()', 'st.session_state.us_ticker_map'))
    elif '_us_map = get_us_ticker_map()' in line:
        new_lines.append(line.replace('get_us_ticker_map()', 'st.session_state.us_ticker_map'))
    elif '_kr_map = get_kr_code_to_name_map()' in line:
        new_lines.append(line.replace('get_kr_code_to_name_map()', 'st.session_state.kr_code_to_name'))
    else:
        new_lines.append(line)

with open(target_file, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Removed {removed_count} local imports and fixed assignments.")
