"""Print each line's painted width: measure_lines.py 'text with \\n'"""
import sys
sys.path.insert(0, "/Users/max/Work/Pet/3ds-ua/tools")
from validate import load_widths, line_widths
from build import apply_homoglyphs, load_homoglyphs
t = sys.argv[1].replace("\\n", "\n")
for line, w in zip(t.split("\n"), line_widths(apply_homoglyphs(t, load_homoglyphs()), load_widths())):
    print(f"{w:6.1f}  {line}")
