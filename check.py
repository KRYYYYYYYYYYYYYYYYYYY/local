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
EXTERNAL_SOURCE_URL = "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt"
GRACE_PERIOD = 2 * 24 * 60 * 60 # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Прив
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}


def rebuild_link_name(link: str, new_name: str) -> str:
    """
    Обновляет только имя узла (часть после #) в vless-ссылке.

    Логика:
    - сохраняет префикс фрагмента до первого "+" или "%20"
      (например флаг-эмодзи в URL-кодировке);
    - заменяет текстовое имя на new_name;
    - если во фрагменте нет разделителя, просто ставит новый фрагмент целиком.
    """
    base, _, fragment = link.partition("#")
    encoded_name = urllib.parse.quote(new_name)

    if not fragment:
        return f"{base}#{encoded_name}"

    plus_pos = fragment.find("+")
    space_pos = fragment.find("%20")

    split_positions = [pos for pos in (plus_pos, space_pos) if pos != -1]
    if not split_positions:
        return f"{base}#{encoded_name}"

    split_pos = min(split_positions)
    separator = "+" if split_pos == plus_pos else "%20"
    prefix = fragment[:split_pos]

    return f"{base}#{prefix}{separator}{encoded_name}"

def is_ipv6(host: str) -> bool:
    return ":" in host

def extract_host_port(link: str):
    # Поиск для обычного хоста или домена
    match = re.search(r"(@)([\w.-]+):(\d+)", link)
    if match:
        # group(0) содержит '@host:port', group(2) - host, group(3) - port
        return match.group(0), match.group(2), match.group(3)
    
    # Поиск для IPv6 в скобках
    ipv6_match = re.search(r"(@)\[([0-9a-fA-F:]+)\]:(\d+)", link)
    if ipv6_match:
        return ipv6_match.group(0), ipv6_match.group(2), ipv6_match.group(3)
        
    return None, None, None


def format_uri_host(host: str) -> str:
    if is_ipv6(host) and not host.startswith("["):
        return f"[{host}]"
    return host

def get_country_code(host: str) -> str:
    try:
        url = f"http://ip-api.com/json/{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except: pass
    return "Unknown"

def fetch_external_servers() -> list:
    if not EXTERNAL_SOURCE_URL.strip(): return []
    try:
        print(f"📥 Загрузка из {EXTERNAL_SOURCE_URL}...")
        with urllib.request.urlopen(EXTERNAL_SOURCE_URL, timeout=8) as response:
            return response.read().decode("utf-8").splitlines()
    except: return []

def main():
    # 1. Загрузка базы и истории
    current_base = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            current_base = f.read().splitlines()

    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: history = json.load(f)
        except: history = {}

    external_servers = fetch_external_servers()
    all_lines = current_base + external_servers
    unique_links = list(dict.fromkeys(line.strip() for line in all_lines if line.strip().startswith("vless://")))

    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1

    print(f"🔄 Проверка {len(unique_links)} строк...")

    for link in unique_links:
        # --- НАЧАЛО БЛОКА ВНУТРИ ЦИКЛА for link in unique_links ---
        base_part = link.split("#", 1)[0].strip()
        endpoint, host, port = extract_host_port(base_part)
        
        if not endpoint or not host or not port:
            continue

        resolved_ip = None
        is_alive = False

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
            # 1. В базу (1.txt) — только чистую часть без имени
            working_for_base.append(base_part)
            
            # 2. Для подписки: берем исходный 'link' (с флагом!), 
            # меняем в нем домен на IP и обновляем имя через функцию
            resolved_host_str = f"[{resolved_ip}]" if is_ipv6(resolved_ip) else resolved_ip
            sub_link = link.replace(endpoint, f"@{resolved_host_str}:{port}", 1)
            
            working_for_sub.append(rebuild_link_name(sub_link, f"wifi {counter}"))
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            # Логика DOWN
            fail_time = history.get(base_part, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_part)
                new_history[base_part] = fail_time
                
                # ОПЯТЬ берем исходный 'link', чтобы флаг не пропал в DOWN
                working_for_sub.append(rebuild_link_name(link, f"wifi {counter} (DOWN)"))
                print(f"⏳ DOWN: {host}")
                counter += 1
            else:
                print(f"🗑️ Удален: {host}")
        # --- КОНЕЦ БЛОКА ---

        # --- КОНЕЦ БЛОКА ПРОВЕРКИ ---

    # 3. Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(working_for_base))
    with open(STATUS_FILE, "w") as f: json.dump(new_history, f)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово! Подписка обновлена.")

if __name__ == "__main__":
    main()
