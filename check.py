import socket
import re
import os
import json
import urllib.parse
import urllib.request
import time

# Настройки путей
INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
STATUS_FILE = 'test1/status.json'
EXTERNAL_SOURCE_URL = ""
GRACE_PERIOD = 2 * 24 * 60 * 60 # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для использования на wifi.
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def is_ipv6(host: str) -> bool:
    return ":" in host

def extract_host_port(link: str):
    # Ищем стандартный формат @host:port
    match = re.search(r"@([\w.-]+):(\d+)", link)
    if match: return match.group(1), match.group(2)
    # Ищем IPv6 формат @[...]:port
    ipv6_match = re.search(r"@\[([0-9a-fA-F:]+)\]:(\d+)", link)
    if ipv6_match: return ipv6_match.group(1), ipv6_match.group(2)
    return None, None

def get_country_code(host: str) -> str:
    try:
        url = f"http://ip-api.com{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except: pass
    return "Unknown"

def main():
    # 1. Загрузка базы
    current_base = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            current_base = f.read().splitlines()

    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: history = json.load(f)
        except: history = {}

    # 2. Сбор ссылок
    all_lines = list(dict.fromkeys(line.strip() for line in current_base if line.strip().startswith("vless://")))

    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1

    print(f"🔄 Проверка {len(all_lines)} серверов...")

    for link in all_lines:
        # ИСПРАВЛЕНО: Четко отделяем всё, что до знака # (сама ссылка со всеми флагами)
        parts = link.split('#', 1)
        base_link_with_flags = parts[0].strip() # Это vless://uuid@host:port?flags...
        
        host, port = extract_host_port(base_link_with_flags)
        if not host or not port: continue

        resolved_ip = None
        is_alive = False

        # Проверка
        if not is_ipv6(host):
            if get_country_code(host) not in BLOCKED_COUNTRIES:
                try:
                    resolved_ip = socket.gethostbyname(host)
                    with socket.create_connection((resolved_ip, int(port)), timeout=2.5):
                        is_alive = True
                except: pass
        else:
            try:
                with socket.create_connection((host, int(port)), timeout=2.5):
                    is_alive = True
                    resolved_ip = host
            except: pass

        if is_alive:
            # ОК: Сохраняем оригинал в 1.txt
            working_for_base.append(base_link_with_flags)
            
            # В подписку меняем хост на IP и ставим имя
            sub_link = base_link_with_flags.replace(f"@{host}:{port}", f"@{resolved_ip}:{port}")
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{sub_link}#{new_name}")
            
            print(f"✅ ОК: {host} ({resolved_ip})")
            counter += 1
        else:
            # FALLBACK: логика 2-х дней
            fail_time = history.get(base_link_with_flags, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_link_with_flags)
                new_history[base_link_with_flags] = fail_time
                new_name = urllib.parse.quote(f"wifi {counter} (DOWN)")
                working_for_sub.append(f"{base_link_with_flags}#{new_name}")
                counter += 1
                print(f"⏳ DOWN: {host}")
            else:
                print(f"🗑️ УДАЛЕН: {host}")

    # 3. Запись
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))
    
    with open(STATUS_FILE, "w") as f:
        json.dump(new_history, f)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово! Проверьте подписку.")

if __name__ == "__main__":
    main()
