import socket
import re
import os
import json
import urllib.parse
import urllib.request

# Настройки путей
INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
# Ссылка на RAW-файл (вставьте, если нужно)
EXTERNAL_SOURCE_URL = ""

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Нумерованная, без IPv6 и RU/CN)
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def is_ipv6(host: str) -> bool:
    return ":" in host

def extract_host_port(link: str):
    """Достает host/port из vless-ссылки, включая IPv6."""
    # Стандартный формат @host:port
    match = re.search(r"@([\w.-]+):(\d+)", link)
    if match:
        return match.group(1), match.group(2)
    # Формат IPv6 @[2001:db8::1]:443
    ipv6_match = re.search(r"@\[([0-9a-fA-F:]+)\]:(\d+)", link)
    if ipv6_match:
        return ipv6_match.group(1), ipv6_match.group(2)
    return None, None

def get_country_code(host: str) -> str:
    try:
        url = f"http://ip-api.com/json/{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except Exception:
        pass
    return "Unknown"

def check_server_smart(host: str, port: str) -> bool:
    if is_ipv6(host):
        print(f"⏩ Пропуск IPv6: {host}")
        return False
    
    country = get_country_code(host)
    if country in BLOCKED_COUNTRIES:
        print(f"🚩 Пропуск {country} (No ChatGPT): {host}")
        return False

    try:
        # Проверка DNS и порта
        ip_address = socket.gethostbyname(host)
        with socket.create_connection((ip_address, int(port)), timeout=2.5):
            return True
    except Exception:
        return False

def fetch_external_servers() -> list:
    if not EXTERNAL_SOURCE_URL.strip():
        return []
    try:
        print(f"📥 Загрузка из {EXTERNAL_SOURCE_URL}...")
        with urllib.request.urlopen(EXTERNAL_SOURCE_URL, timeout=8) as response:
            return response.read().decode("utf-8").splitlines()
    except Exception:
        print("⚠️ Ошибка загрузки внешних серверов")
        return []

def main():
    # 1. Загрузка локальной базы
    current_base = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            current_base = f.read().splitlines()

    # 2. Сбор всех уникальных ссылок
    external_servers = fetch_external_servers()
    all_lines = current_base + external_servers
    # Чистим дубликаты, сохраняя порядок
    unique_links = list(dict.fromkeys(line.strip() for line in all_lines if line.strip().startswith("vless://")))

    working_for_base = []
    working_for_sub = []
    counter = 1

    print(f"Начинаю проверку {len(unique_links)} уникальных строк...")

    for link in unique_links:
        # Убираем старое имя сервера для проверки
        base_part = link.split("#")[0].strip()
        host, port = extract_host_port(base_part)
        
        if not host or not port:
            continue

        if check_server_smart(host, port):
            # Сохраняем "чистую" ссылку в базу 1.txt
            working_for_base.append(base_part)
            # Создаем пронумерованную ссылку для wifi.txt
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{base_part}#{new_name}")
            
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1

    # 3. Сохранение результатов
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово! В базе и подписке осталось {len(working_for_sub)} серверов.")

if __name__ == "__main__":
    main()
