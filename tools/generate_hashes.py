import bcrypt
import json

# 原始用户凭据
user_credentials = {}

# 生成哈希密码
hashed_credentials = {}
for username, password in user_credentials.items():
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    hashed_credentials[username] = hashed.decode('utf-8')

# 写入文件
with open('../user_credentials.json', 'w') as f:
    json.dump(hashed_credentials, f, indent=2)

print("已生成并更新用户凭据文件!")
