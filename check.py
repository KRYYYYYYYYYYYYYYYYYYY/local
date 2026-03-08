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
GRACE_PERIOD = 2 * 24 * 60 * 60  # 2 дня

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Reality Флаги Сохранены | Hard-Resolve IP
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

    print(f"🔄 Проверка {len(unique_links)} строк...")

    for full_link in unique_links:
        # 1. Сначала полностью очищаем ссылку от старого названия (всё что после #)
        # Это нужно, чтобы в 1.txt не плодились "wifi 1", "wifi 2"
        base_link_no_name = full_link.split('#')[0]

        # 2. Ищем @хост:порт во всей этой длинной строке
        match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", base_link_no_name)
        if not match: continue
        
        original_part = match.group(0) # Например: @ee.harknmav.fun:443
        host = match.group(1).strip('[]')
        port = match.group(2)

        resolved_ip = None
        is_alive = False

        # Проверка (пропуск RU/CN и IPv6)
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
            # СОХРАНЕНИЕ: Пишем в базу версию со всеми параметрами (?pbk=...&sid=...)
            working_for_base.append(base_link_no_name)
            
            # В подписку: меняем домен на IP внутри всей строки
            target_part = f"@{resolved_ip}:{port}"
            sub_link = base_link_no_name.replace(original_part, target_part)
            
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{sub_link}#{new_name}")
            
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            # Логика 2-х дней
            fail_time = history.get(base_link_no_name, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_link_no_name)
                new_history[base_link_no_name] = fail_time
                new_name = urllib.parse.quote(f"wifi {counter} (DOWN)")
                working_for_sub.append(f"{base_link_no_name}#{new_name}")
                counter += 1
                print(f"⏳ DOWN: {host}")
            else:
                print(f"🗑️ УДАЛЕН: {host}")

    # Запись
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
