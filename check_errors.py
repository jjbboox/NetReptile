import re

with open('temp/透视之眼.txt', 'r', encoding='utf-8') as f:
    content = f.read()
    
pattern = r'={80}\s*\nERROR - Failed to process URL: (.+?)\s*\n={80}'
matches = list(re.finditer(pattern, content, re.DOTALL))
print(f'在temp/透视之眼.txt中找到 {len(matches)} 个错误块')
for i, match in enumerate(matches[:3], 1):
    print(f'错误块 {i}: {match.group(1)}')
