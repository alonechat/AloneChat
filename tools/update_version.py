#!/usr/bin/env python3
"""
版本号更新工具
支持4位版本号格式(主版本.次版本.补丁版本.构建版本)
"""
import os
import re

# 定义版本号文件路径
VERSION_FILE = os.path.join(os.path.dirname(__file__), 'AloneChat', '__init__.py')

# 读取当前版本号
with open(VERSION_FILE, 'r') as f:
    content = f.read()

# 提取版本号（支持3位或4位格式）
version_match = re.search(r'__version__ = "([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)"', content)
if not version_match:
    print("未找到版本号定义")
    exit(1)

current_version = version_match.group(1)
print(f"当前版本: {current_version}")

# 分解版本号并增加构建版本
version_parts = list(map(int, current_version.split('.')))

# 确保版本号至少有3位
while len(version_parts) < 4:
    version_parts.append(0)

# 增加构建版本号
version_parts[3] += 1

# 构建新版本号
new_version = '.'.join(map(str, version_parts))
print(f"新版本: {new_version}")

# 更新版本号
new_content = re.sub(r'__version__ = "[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?"', f'__version__ = "{new_version}"', content)

# 写回文件
with open(VERSION_FILE, 'w') as f:
    f.write(new_content)

print(f"版本号已更新至 {new_version}")
