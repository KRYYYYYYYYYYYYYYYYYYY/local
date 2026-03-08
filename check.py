import socket
import re
import os
import json
import time
import urllib.parse
import urllib.request

# Настройки путей
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
GRACE_PERIOD = 2 * 24 * 60 * 60  # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: SID любой длины сохранен | Hard-Resolve IP
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def get_country_code(host: str) -> str:
    url = f"http://ip-api.com/json/{host}?fields=status,countryCode"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except:
        pass
    return "Unknown"

def extract_host_port(link: str):
    match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", link)
    if not match:
        return None, None, None
    return match.group(0), match.group(1).strip("[]"), match.group(2)

def trim_to_sid_value(link: str) -> str:
    """Обрезает старое название, сохраняя sid полностью."""
    sid_pos = link.find("sid=")
    if sid_pos == -1:
        # Если sid нет, просто берем всё до первой решетки, плюса или пробела
        return re.split(r"[#+ ]", link)[0]

    scan_from = sid_pos + 4
    # Ищем первый разделитель ПОСЛЕ значения sid
    delimiters = ["+", "%20", "#", " "]
    positions = []
    for d in delimiters:
        pos = link.find(d, scan_from)
        if pos != -1:
            positions.append(pos)
    
    end_pos = min(positions) if positions else len(link)
    return link[:end_pos]

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = {}

    unique_links = list(dict.fromkeys(line.strip() for line in lines if line.strip().startswith("vless://")))
    
    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1

    print(f"🔄 Проверка {len(unique_links)} уникальных строк...")

    for link in unique_links:
        # 1. Сохраняем техническую часть (до начала названия)
        base_part = trim_to_sid_value(link)
        
        orig_hp, host, port = extract_host_port(base_part)
        if not orig_hp:
            continue

        # 2. Фильтр стран
        if ":" not in host and get_country_code(host) in BLOCKED_COUNTRIES:
            print(f"🚩 Пропуск (RU/CN): {host}")
            continue

        resolved_ip = None
        is_alive = False

        try:
            resolved_ip = socket.gethostbyname(host) if ":" not in host else host
            with socket.create_connection((resolved_ip, int(port)), timeout=2.5):
                is_alive = True
        except:
            is_alive = False

        if is_alive:
            working_for_base.append(base_part)
            # Hard-Resolve: замена в подписке
            sub_link = base_part.replace(orig_hp, f"@{resolved_ip}:{port}", 1)
            working_for_sub.append(f"{sub_link}+wifi+{counter}")
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            # Логика 2 дня
            fail_time = history.get(base_part, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_part)
                new_history[base_part] = fail_time
                working_for_sub.append(f"{base_part}+wifi+{counter}+(DOWN)")
                print(f"⏳ DOWN: {host}")
                counter += 1

    # Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово! Сохранено: {len(working_for_sub)}")

if __name__ == "__main__":
    main()
