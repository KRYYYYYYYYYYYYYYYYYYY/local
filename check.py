import socket, re, os, json, time, urllib.parse, urllib.request

# Настройки
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
EXTERNAL_SOURCE_URL = "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt"
GRACE_PERIOD = 2 * 24 * 60 * 60 # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Авто-сбор (2ч) | SID сохранен | Hard-Resolve
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

def fetch_external():
    if not EXTERNAL_SOURCE_URL: return []
    try:
        print("📥 Качаю сервера из внешнего репо...")
        with urllib.request.urlopen(EXTERNAL_SOURCE_URL, timeout=10) as r:
            return r.read().decode("utf-8").splitlines()
    except: return []

def rebuild_link_name(link, counter, suffix=""):
    """Обновляет имя после эмодзи/флага"""
    base, _, fragment = link.partition("#")
    if not fragment: return f"{base}#+wifi+{counter}{suffix}"
    
    # Сохраняем эмодзи (всё до первого + или %20)
    match = re.search(r"^(.*?)(?:\+|\s|%20)", fragment)
    prefix = match.group(1) if match else fragment
    return f"{base}#{prefix}+wifi+{counter}{suffix}"

def main():
    local_lines = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f: local_lines = f.read().splitlines()
    
    external_lines = fetch_external()
    # Объединяем и чистим дубли
    all_links = list(dict.fromkeys([l.strip() for l in (local_lines + external_lines) if l.strip().startswith("vless://")]))
    
    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: history = json.load(f)
        except: history = {}

    working_for_base, working_for_sub, new_history = [], [], {}
    now, counter = time.time(), 1

    for link in all_links:
        # Убираем старое имя для базы и поиска host/port
        base_link = link.split('#')[0]
        match = re.search(r"@([\w.-]+|\[[0-9a-fA-F:]+\]):(\d+)", base_link)
        if not match: continue
        orig_hp, host, port = match.group(0), match.group(1).strip("[]"), match.group(2)

        if ":" not in host and get_country_code(host) in BLOCKED_COUNTRIES: continue

        resolved_ip, is_alive = None, False
        try:
            resolved_ip = socket.gethostbyname(host) if ":" not in host else host
            with socket.create_connection((resolved_ip, int(port)), timeout=2.5): is_alive = True
        except: is_alive = False

        if is_alive:
            working_for_base.append(base_link)
            res_link = base_link.replace(orig_hp, f"@{resolved_ip}:{port}", 1)
            # Если в оригинальной ссылке был флаг-эмодзи, сохраняем его
            working_for_sub.append(rebuild_link_name(link.replace(orig_hp, f"@{resolved_ip}:{port}", 1), counter))
            print(f"✅ ОК: {host}")
            counter += 1
        else:
            fail_time = history.get(base_link, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_link)
                new_history[base_link] = fail_time
                working_for_sub.append(rebuild_link_name(link, counter, "+(DOWN)"))
                counter += 1

    # Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(working_for_base))
    with open(STATUS_FILE, "w") as f: json.dump(new_history, f, indent=2)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write(HEADER + "\n".join(working_for_sub))

if __name__ == "__main__":
    main()
