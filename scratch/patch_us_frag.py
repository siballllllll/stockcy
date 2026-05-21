import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_us_loop = False
us_loop_indent = ""
i = 0
while i < len(lines):
    line = lines[i]
    if "for us_sub_name, us_stocks in us_subsectors.items():" in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(indent + "@st.fragment\n")
        new_lines.append(indent + "def _render_us_subsector_card(us_sub_name, us_stocks, us_prices, us_ticker_locations, us_selected_sector):\n")
        
        # Now we process all lines inside the loop
        j = i + 1
        inner_lines = []
        while j < len(lines):
            inner_line = lines[j]
            if inner_line.strip() == "" or inner_line.startswith(indent + "    "):
                if "st.rerun()" in inner_line and "scope" not in inner_line and "st.session_state[us_tok] = not us_is_open" in lines[j-1]:
                    inner_lines.append(inner_line.replace("st.rerun()", "st.rerun(scope=\"fragment\")"))
                elif "st.session_state[us_ai_key] = _us_sub_ai_summary" in inner_line:
                    # Need to add spinner and rerun for AI button
                    ws = inner_line[:len(inner_line) - len(inner_line.lstrip())]
                    inner_lines.append(ws + "with st.spinner(\"AI 분석 중...\"):\n")
                    inner_lines.append(ws + "    " + inner_line.lstrip())
                    # The function call spans 3 lines, let's just collect them
                    k = j + 1
                    while k < len(lines) and lines[k].strip() and not lines[k].strip().startswith("if us_is_open:"):
                        inner_lines.append(ws + "    " + lines[k].lstrip())
                        if ")" in lines[k]:
                            break
                        k += 1
                    inner_lines.append(ws + "st.rerun(scope=\"fragment\")\n")
                    j = k
                else:
                    inner_lines.append(inner_line)
                j += 1
            else:
                break
        
        # Now extend inner_lines
        new_lines.extend(inner_lines)
        
        # Then call it
        new_lines.append(indent + "for us_sub_name, us_stocks in us_subsectors.items():\n")
        new_lines.append(indent + "    _render_us_subsector_card(us_sub_name, us_stocks, us_prices, us_ticker_locations, us_selected_sector)\n")
        
        i = j - 1
    else:
        new_lines.append(line)
    i += 1

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("done")
