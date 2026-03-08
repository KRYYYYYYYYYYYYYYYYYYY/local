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
GRACE_PERIOD = 2 * 24 * 60 * 60  # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Hard-Resolve IP | SID и Reality Флаги Сохранены
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

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
    if not os.path.exists(INPUT_FILE): return
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        current_base = f.read().splitlines()

    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: history = json.load(f)
        except: history = {}

    unique_links = list(dict.fromkeys(line.strip() for line in current_base if line.strip().startswith("vless://")))

    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1

    for link in unique_links:
        # ИСПРАВЛЕНИЕ: Мы НЕ используем split('#'), чтобы не отрезать кусок sid.
        # Мы просто находим позицию ПОСЛЕДНЕЙ решетки, если она есть.
        last_hash_index = link.rfind('#')
        if last_hash_index != -1:
            # Ссылка до названия (со всеми флагами и sid)
            base_link_with_all_flags = link[:last_hash_index]
        else:
            base_link_with_all_flags = link

        # Поиск хоста и порта для проверки и Hard-Resolve
        match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", base_link_with_all_flags)
        if not match: continue
        
        original_host_port = match.group(0)
        host = match.group(1).strip('[]')
        port = match.group(2)

        resolved_ip = None
        is_alive = False

        if ":" not in host:
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
            # Сохраняем в базу версию со ВСЕМИ флагами (включая полный sid)
            working_for_base.append(base_link_with_all_flags)
            
            # В подписку: Hard-Resolve (замена домена на IP)
            target_host_port = f"@{resolved_ip}:{port}"
            final_sub_link = base_link_with_all_flags.replace(original_host_port, target_host_port)
            
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{final_sub_link}#{new_name}")
            
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            fail_time = history.get(base_link_with_all_flags, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_link_with_all_flags)
                new_history[base_link_with_all_flags] = fail_time
                new_name = urllib.parse.quote(f"wifi {counter} (DOWN)")
                working_for_sub.append(f"{base_link_with_all_flags}#{new_name}")
                counter += 1
                print(f"⏳ DOWN: {host}")

    # Запись результатов
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))
    with open(STATUS_FILE, "w") as f:
        json.dump(new_history, f)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

if __name__ == "__main__":
    main()
