import os
import re
import html
import socket
import ssl
import time
from datetime import datetime

# =====================================================
# НАСТРОЙКИ (УКАЖИ СВОИ ПАПКИ)
# =====================================================

# Папка, где лежат .txt файлы с ключами
KEYS_FOLDER = r"PATH_TO_KEYS_FOLDER"

# Папка, куда сохранять результат и логи
NEW_KEYS_FOLDER = r"PATH_TO_OUTPUT_FOLDER"

# Тайминги
TIMEOUT = 5    # таймаут соединения (сек)
RETRIES = 2    # количество попыток на один ключ

# =====================================================

os.makedirs(NEW_KEYS_FOLDER, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LIVE_KEYS_FILE = os.path.join(NEW_KEYS_FOLDER, f"live_keys_{timestamp}.txt")
LOG_FILE = os.path.join(NEW_KEYS_FOLDER, f"log_{timestamp}.txt")

# ------------------ ЛОГ ------------------
def log(msg: str):
    print(msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
    except Exception:
        pass

# ------------------ ВСПОМОГАТЕЛЬНОЕ ------------------
def decode_html_entities(key: str) -> str:
    return html.unescape(key)

def load_all_keys(folder: str):
    keys = []
    if not os.path.isdir(folder):
        log(f"[ERROR] Keys folder not found: {folder}")
        return keys

    for file in os.listdir(folder):
        if file.lower().endswith(".txt"):
            path = os.path.join(folder, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            keys.append(line)
                log(f"[OK] Loaded: {file}")
            except Exception as e:
                log(f"[ERROR] Read failed {file}: {e}")
    return keys

def remove_duplicates(keys):
    return list(dict.fromkeys(keys))

def prepare_keys(keys):
    return [decode_html_entities(k).strip() for k in keys]

def detect_key_type(key: str) -> str:
    k = key.lower()
    if k.startswith("vless://"):
        return "VLESS"
    if k.startswith("vmess://"):
        return "VMESS"
    if k.startswith("ss://"):
        return "SS"
    if k.startswith("trojan://"):
        return "TROJAN"
    return "UNKNOWN"

def check_key_format(key: str) -> bool:
    t = detect_key_type(key)
    if t in ("VLESS", "VMESS", "TROJAN"):
        return bool(re.search(r'@([\w\.-]+):(\d+)', key))
    if t == "SS":
        return bool(re.match(r'ss://[\w\-_=]+@[\w\.-]+:\d+', key))
    return False

def extract_host_port(key: str):
    try:
        if key.startswith(("vless://", "vmess://", "trojan://")):
            m = re.search(r'@([\w\.-]+):(\d+)', key)
            if m:
                return m.group(1), int(m.group(2))
        if key.startswith("ss://"):
            m = re.match(r'ss://[\w\-_=]+@([\w\.-]+):(\d+)', key)
            if m:
                return m.group(1), int(m.group(2))
    except Exception:
        pass
    return None, None

def classify_latency(ms: int) -> str:
    if ms < 100:
        return "good"
    if ms <= 300:
        return "normal"
    return "weak"

def measure_latency(host, port, use_tls=False):
    results = []
    for _ in range(RETRIES):
        start = time.time()
        try:
            if use_tls:
                ctx = ssl.create_default_context()
                with socket.create_connection((host, port), timeout=TIMEOUT) as s:
                    with ctx.wrap_socket(s, server_hostname=host):
                        pass
            else:
                with socket.create_connection((host, port), timeout=TIMEOUT):
                    pass
            results.append(int((time.time() - start) * 1000))
        except Exception:
            continue
    return min(results) if results else None

# ------------------ ОСНОВНОЙ ПРОЦЕСС ------------------
log("=== KEY CHECKER START ===")

keys = load_all_keys(KEYS_FOLDER)
keys = remove_duplicates(keys)
keys = prepare_keys(keys)

live = []

for i, key in enumerate(keys, 1):
    t = detect_key_type(key)

    if not check_key_format(key):
        log(f"[{i}] BAD FORMAT ({t})")
        continue

    host, port = extract_host_port(key)
    if not host:
        log(f"[{i}] HOST PARSE ERROR ({t})")
        continue

    use_tls = "tls" in key.lower() or t == "TROJAN"
    latency = measure_latency(host, port, use_tls)

    if latency is None:
        log(f"[{i}] DEAD {host}:{port}")
        continue

    quality = classify_latency(latency)
    live.append((latency, quality, t, host, port, key))
    log(f"[{i}] OK {host}:{port} {latency}ms {quality}")

live.sort(key=lambda x: x[0])

with open(LIVE_KEYS_FILE, "w", encoding="utf-8") as f:
    for latency, quality, t, host, port, key in live:
        f.write(f"{latency}ms | {quality} | {t} | {host}:{port} | {key}\n")

log(f"FINISHED. LIVE KEYS: {len(live)}")
