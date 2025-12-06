import bcrypt
import json

# Original user IDs
user_credentials = {}

# Hashing
hashed_credentials = {}
for username, password in user_credentials.items():
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    hashed_credentials[username] = hashed.decode('utf-8')

# Write
with open('../user_credentials.json', 'w') as f:
    json.dump(hashed_credentials, f, indent=2)

print("Updated!")
