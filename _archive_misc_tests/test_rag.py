import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ai_engine import generate_macro_phase_analysis

if __name__ == "__main__":
    result = generate_macro_phase_analysis()
    print(result)
