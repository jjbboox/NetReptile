import re
import sys

if len(sys.argv) < 2:
    print("用法: python check_fixed_file.py <文件名>")
    sys.exit(1)

filename = sys.argv[1]

try:
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'={80}\s*\nERROR - Failed to process URL: (.+?)\s*\n={80}'
    matches = list(re.finditer(pattern, content, re.DOTALL))
    
    if len(matches) == 0:
        print(f'✓ 文件 {filename} 中没有发现错误块 - 修复成功！')
    else:
        print(f'✗ 在 {filename} 中找到 {len(matches)} 个错误块')
        for i, match in enumerate(matches[:5], 1):
            print(f'  错误块 {i}: {match.group(1)}')
        if len(matches) > 5:
            print(f'  ... 还有 {len(matches)-5} 个错误块')
            
except FileNotFoundError:
    print(f"错误: 文件 {filename} 不存在")
except Exception as e:
    print(f"错误: {e}")
