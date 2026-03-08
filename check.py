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
# announce: Флаги бебебеб сохранены | Hard-Resolve IP | Ожидание 2 дня
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

    print(f"🔄 Проверка {len(unique_links)} серверов...")

    for link in unique_links:
        # 1. Отделяем техническую часть от названия (если оно было)
        # Нам нужно сохранить ВСЁ до последнего знака #
        if '#' in link:
            full_link_with_flags = link.rsplit('#', 1)[0]
        else:
            full_link_with_flags = link

        # 2. Ищем host и port
        match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", full_link_with_flags)
        if not match: continue
        
        original_host_port = match.group(0) # Наприм: @ee.harknmav.fun:443
        host = match.group(1).strip('[]')
        port = match.group(2)

        resolved_ip = None
        is_alive = False

        # Проверка
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
            # Сохраняем в базу 1.txt версию СО ВСЕМИ ФЛАГАМИ
            working_for_base.append(full_link_with_flags)
            
            # В подписку меняем домен на IP, сохраняя всё остальное
            target_host_port = f"@{resolved_ip}:{port}"
            sub_link = full_link_with_flags.replace(original_host_port, target_host_port)
            
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{sub_link}#{new_name}")
            
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            # Логика 2-х дней
            fail_time = history.get(full_link_with_flags, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(full_link_with_flags)
                new_history[full_link_with_flags] = fail_time
                new_name = urllib.parse.quote(f"wifi {counter} (DOWN)")
                working_for_sub.append(f"{full_link_with_flags}#{new_name}")
                counter += 1
                print(f"⏳ DOWN: {host}")
            else:
                print(f"🗑️ УДАЛЕН: {host}")

    # Запись файлов
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))
    
    with open(STATUS_FILE, "w") as f:
        json.dump(new_history, f)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово!")

if __name__ == "__main__":
    main()
