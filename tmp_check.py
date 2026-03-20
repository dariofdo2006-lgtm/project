import re
from ast import parse, FunctionDef, ClassDef

with open(r"c:\Users\disan\mini p1\python-budget-calendar\main.py", "r", encoding="utf-8") as f:
    code = f.read()

tree = parse(code)
defined_funcs = []
for node in tree.body:
    if isinstance(node, ClassDef):
        for n in node.body:
            if isinstance(n, FunctionDef):
                if n.name != "__init__":
                    defined_funcs.append(n.name)
    elif isinstance(node, FunctionDef):
        if n.name != "__init__":
            defined_funcs.append(node.name)

print("Functions defined:", defined_funcs)
for func in defined_funcs:
    # A very basic check: does the function name appear more than once (once for definition, once for call)?
    # we need to check if count > 1
    count = code.count(func)
    if count <= 1:
        print(f"UNUSED FUNCTION: {func}")
