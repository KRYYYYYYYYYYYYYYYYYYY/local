import socket, re, os, json, time, urllib.parse, urllib.request

INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
GRACE_PERIOD = 2 * 24 * 60 * 60 

HEADER = """# profile-title: 🏴WIFI🏴
# announce: SID любой длины сохранен | Hard-Resolve IP
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def get_country_code(host):
    try:
        url = f"http://ip-api.com{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=3) as r:
            data = json.loads(r.read().decode())
            return data.get("countryCode", "Unknown") if data.get("status") == "success" else "Unknown"
    except: return "Unknown"

def main():
    if not os.path.exists(INPUT_FILE): return
    with open(INPUT_FILE, "r", encoding="utf-8") as f: lines = f.read().splitlines()
    
    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: history = json.load(f)
        except: history = {}

    unique_links = list(dict.fromkeys(l.strip() for l in lines if l.strip().startswith("vless://")))
    working_for_base, working_for_sub, new_history = [], [], {}
    now, counter = time.time(), 1

    for link in unique_links:
        # 1. Извлекаем host:port для Hard-Resolve
        match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", link)
        if not match: continue
        orig_hp, host, port = match.group(0), match.group(1).strip("[]"), match.group(2)

        if ":" not in host and get_country_code(host) in BLOCKED_COUNTRIES: continue

        resolved_ip, is_alive = None, False
        try:
            resolved_ip = socket.gethostbyname(host) if ":" not in host else host
            with socket.create_connection((resolved_ip, int(port)), timeout=2.5): is_alive = True
        except: is_alive = False

        # 2. ЛОГИКА СОХРАНЕНИЯ SID (Любой длины)
        # Ищем sid= и забираем ВСЁ до первого разделителя (+, %20, #) или конца строки
        # Шаблон: (.*?sid=[^+#% ]+) - Группа 1: всё до конца значения sid
        # Остальное (имя) просто игнорируем
        sid_match = re.search(r"(.*?sid=[^+#% ]+)", link)
        
        if sid_match:
            # base_part содержит vless://...sid=ЗНАЧЕНИЕ_ЛЮБОЙ_ДЛИНЫ
            base_part = sid_match.group(1)
        else:
            # Если sid нет (мало ли), режем по старинке до первой решетки или пробела
            base_part = re.split(r'[#+ ]', link)[0]

        if is_alive:
            working_for_base.append(base_part)
            # Hard-Resolve (замена домена на IP) в базе
            sub_link = base_part.replace(orig_hp, f"@{resolved_ip}:{port}", 1)
            # Приклеиваем НОВОЕ имя
            working_for_sub.append(f"{sub_link}+wifi+{counter}")
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            fail_time = history.get(base_part, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_part)
                new_history[base_part] = fail_time
                working_for_sub.append(f"{base_part}+wifi+{counter}+(DOWN)")
                counter += 1

    # Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(working_for_base))
    with open(STATUS_FILE, "w") as f: json.dump(new_history, f, indent=2)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write(HEADER + "\n".join(working_for_sub))

if __name__ == "__main__":
    main()
