import re
import json

TEMPLATE_VAR_PATTERN = r"\{\{\s*([^|}]*?)(?:\s*\|\s*([^:}]+)(?::([^}]+))?)?\s*\}\}"
template_str = 'Welcome to the workflow tester. {{ var }}'
def _replace(match):
    print("MATCH GROUP 1:", match.group(1))
    return 'X'

print("SUB:", re.sub(TEMPLATE_VAR_PATTERN, _replace, template_str))

s2 = 'No brackets'
print("SUB2:", re.sub(TEMPLATE_VAR_PATTERN, _replace, s2))
