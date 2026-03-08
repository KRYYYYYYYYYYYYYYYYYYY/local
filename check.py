import socket, re, os, json, time, urllib.parse, urllib.request

INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
GRACE_PERIOD = 2 * 24 * 60 * 60 

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Hard-Resolve IP | SID СОХРАНЕН | Нумерация исправлена
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
    with open(INPUT_FILE, "r", encoding="utf-8") as f: current_base = f.read().splitlines()
    
    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: history = json.load(f)
        except: history = {}

    unique_links = list(dict.fromkeys(line.strip() for line in current_base if line.strip().startswith("vless://")))
    working_for_base, working_for_sub, new_history = [], [], {}
    now, counter = time.time(), 1

    for link in unique_links:
        # Ищем @host:port
        match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", link)
        if not match: continue
        orig_hp, host, port = match.group(0), match.group(1).strip("[]"), match.group(2)

        if ":" not in host and get_country_code(host) in BLOCKED_COUNTRIES: continue

        resolved_ip, is_alive = None, False
        try:
            resolved_ip = socket.gethostbyname(host) if ":" not in host else host
            with socket.create_connection((resolved_ip, int(port)), timeout=2.5): is_alive = True
        except: is_alive = False

        if is_alive:
            working_for_base.append(link)
            # HARD-RESOLVE
            res_link = link.replace(orig_hp, f"@{resolved_ip}:{port}", 1)
            # ЛОГИКА ИМЕНИ: Ищем "sid=..." и меняем всё, что ПОСЛЕ него
            if "sid=" in res_link:
                # Режем по sid=, берем первые 16 символов значения sid, остальное заменяем
                parts = re.split(r"(sid=[a-fA-F0-9]{1,16})", res_link)
                # parts[0] - начало, parts[1] - "sid=XXX", parts[2] - старое имя
                res_link = f"{parts[0]}{parts[1]}+{urllib.parse.quote(f'wifi+{counter}')}"
            else:
                # Если sid нет, просто нумеруем в конце
                base = res_link.rsplit("#", 1)[0] if "#" in res_link else res_link
                res_link = f"{base}#+wifi+{counter}"
            
            working_for_sub.append(res_link)
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            # Логика 2 дня
            fail_time = history.get(link, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(link)
                new_history[link] = fail_time
                working_for_sub.append(link + "+(DOWN)")
                counter += 1

    with open(INPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(working_for_base))
    with open(STATUS_FILE, "w", encoding="utf-8") as f: json.dump(new_history, f, indent=2)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write(HEADER + "\n".join(working_for_sub))

if __name__ == "__main__":
    main()
