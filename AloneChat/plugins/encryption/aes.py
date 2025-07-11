from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64
from AloneChat.core.plugin import Plugin

class AESEncryptor(Plugin):
    def __init__(self):
        self.key = get_random_bytes(16)

    def encrypt(self, text):
        cipher = AES.new(self.key, AES.MODE_EAX)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(text.encode())
        return base64.b64encode(nonce + tag + ciphertext).decode()

    def decrypt(self, encrypted):
        data = base64.b64decode(encrypted)
        nonce, tag, ciphertext = data[:16], data[16:32], data[32:]
        cipher = AES.new(self.key, AES.MODE_EAX, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()

class PluginImpl(AESEncryptor):
    pass