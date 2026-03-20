import re

file_path = r"c:\Users\disan\mini p1\python-budget-calendar\main.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

def fix_super_init(match):
    line = match.group(0)
    if '# type: ignore' not in line:
        return line.rstrip() + ' # type: ignore\n'
    return line

content = re.sub(r'^(\s*super\(\)\.__init__\(.*?\))\s*\n', fix_super_init, content, flags=re.MULTILINE)

content = content.replace('self.month_expenses: dict = {}', 'self.month_expenses = {}')
content = content.replace('total_income: float = 0.0', 'total_income = 0.0')
content = content.replace('total_expenses: float = 0.0', 'total_expenses = 0.0')
content = content.replace('expenses_monthly: dict = {', 'expenses_monthly = {')
content = content.replace('income_monthly: dict = {', 'income_monthly = {')

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
