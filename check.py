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

EXTERNAL_SOURCE_URL = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_SS%2BAll_RUS.txt"
]

GRACE_PERIOD = 2 * 24 * 60 * 60 # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для использования на wifi.
# profile-update-interval: 2

"""

ALLOWED_COUNTRIES = {"US", "DE", "NL", "GB", "FR", "FI", "SG", "JP", "PL", "TR"}

def rebuild_link_name(link: str, new_name: str) -> str:
    base, _, fragment = link.partition("#")
    if not fragment:
        return f"{base}#{urllib.parse.quote(new_name)}"

    # Декодируем фрагмент (то, что после #), чтобы найти флаг
    fragment_dec = urllib.parse.unquote(fragment)
    
    # Регулярка ищет эмодзи или спецсимволы в начале строки
    # (обычно это и есть флаг)
    match = re.match(r"^([^\w\s\d]|[^\x00-\x7F])+", fragment_dec)
    if match:
        prefix = match.group(0).strip()
        # Возвращаем: База#Флаг + пробел + НовоеИмя
        return f"{base}#{urllib.parse.quote(prefix + ' ' + new_name)}"
    
    # Если флага нет, просто ставим имя
    return f"{base}#{urllib.parse.quote(new_name)}"

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
    # Если вдруг в переменной осталась просто строка, превращаем её в список для совместимости
    urls = [EXTERNAL_SOURCE_URL] if isinstance(EXTERNAL_SOURCE_URL, str) else EXTERNAL_SOURCE_URL
    
    all_configs = []
    for url in urls:
        if not url.strip(): continue
        try:
            print(f"📥 Загрузка из {url}...")
            with urllib.request.urlopen(url, timeout=8) as response:
                configs = response.read().decode("utf-8").splitlines()
                all_configs.extend(configs)
        except Exception as e:
            print(f"❌ Ошибка загрузки {url}: {e}")
    return all_configs

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
        base_part = link.split("#", 1)[0].strip()
        endpoint, host, port = extract_host_port(base_part)
        
        if not endpoint or not host or not port:
            continue

        # --- ЭТАП 1: ПРОВЕРКА ПОРТА ---
        resolved_ip = None
        is_alive = False
        try:
            if not is_ipv6(host):
                resolved_ip = socket.gethostbyname(host)
                with socket.create_connection((resolved_ip, int(port)), timeout=3.0):
                    is_alive = True
            else:
                with socket.create_connection((host, int(port)), timeout=3.0):
                    is_alive = True
                    resolved_ip = host
        except:
            is_alive = False

        # --- ЭТАП 2 И 3: ТОЛЬКО ЕСЛИ ЖИВОЙ ---
        if is_alive:
            # Проверка шифрования
            if "security=none" in base_part.lower():
                print(f"❌ БЕЗ ШИФРОВАНИЯ: {host}")
                continue

            # Проверка страны
            country = get_country_code(host)
            if country not in ALLOWED_COUNTRIES:
                print(f"🗑️ НЕ ТА СТРАНА ({country}): {host}")
                continue 

            # СОХРАНЕНИЕ РАБОЧЕГО
            working_for_base.append(base_part)
            ip_str = f"[{resolved_ip}]" if is_ipv6(resolved_ip) else resolved_ip
            sub_link = link.replace(endpoint, f"@{ip_str}:{port}", 1)
            final_link = rebuild_link_name(sub_link, f"wifi {counter}")
            working_for_sub.append(final_link)
            print(f"✅ ОК ({country}): {host} -> wifi {counter}")
            counter += 1

        else:
            # ЛОГИКА GRACE PERIOD (из твоего исходного кода)
            fail_time = history.get(base_part, now)
            if now - fail_time < GRACE_PERIOD:
                # Проверим страну даже для упавших, чтобы не держать мусор
                country = get_country_code(host)
                if country in ALLOWED_COUNTRIES:
                    working_for_base.append(base_part)
                    new_history[base_part] = fail_time
                    working_for_sub.append(rebuild_link_name(link, f"wifi {counter} (DOWN)"))
                    print(f"⏳ DOWN ({country}): {host}")
                    counter += 1

            else:
                print(f"🗑️ Удален (тайм-аут): {host}")
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
