import socket
import re
import os
import json
import urllib.request
import os
import re
import socket
import urllib.parse
import urllib.request

# Настройки путей
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"

INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
# Ссылка на RAW-файл со списком VLESS-ссылок (по одной в строке).
# Можно оставить пустой строкой, если внешний источник не нужен.
EXTERNAL_SOURCE_URL = ""

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Нумерованная, без IPv6 и RU/CN)
# profile-update-interval: 2

"""

def is_ipv6(host):
    return ":" in host and not host.startswith('[')
BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def get_country_code(host):

def is_ipv6(host: str) -> bool:
    return ":" in host


def extract_host_port(link: str):
    """Достает host/port из vless-ссылки, включая IPv6 в квадратных скобках."""
    # IPv4 / домен
    match = re.search(r"@([\w.-]+):(\d+)", link)
    if match:
        return match.group(1), match.group(2)

    # IPv6: @[2001:db8::1]:443
    ipv6_match = re.search(r"@\[([0-9a-fA-F:]+)\]:(\d+)", link)
    if ipv6_match:
        return ipv6_match.group(1), ipv6_match.group(2)

    return None, None


def get_country_code(host: str) -> str:
    try:
        # Исправлено: добавлен /json/ и правильный формат запроса
        url = f"http://ip-api.com{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                return data.get('countryCode')
    except:
        url = f"http://ip-api.com/json/{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except Exception:
        pass
    return "Unknown"

def check_server_smart(host, port):

def check_server_smart(host: str, port: str) -> bool:
    if is_ipv6(host):
        print(f"⏩ Пропуск IPv6: {host}")
        return False
    

    country = get_country_code(host)
    if country in ['RU', 'CN', 'IR', 'KP']:
    if country in BLOCKED_COUNTRIES:
        print(f"🚩 Пропуск {country} (No ChatGPT): {host}")
        return False

    try:
        ip_address = socket.gethostbyname(host)
        with socket.create_connection((ip_address, int(port)), timeout=2.5):
            return True
    except:
    except Exception:
        return False


def fetch_external_servers() -> list[str]:
    """Скачивает серверы из внешнего источника, если ссылка задана."""
    if not EXTERNAL_SOURCE_URL.strip():
        return []

    parsed = urllib.parse.urlparse(EXTERNAL_SOURCE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("⚠️ EXTERNAL_SOURCE_URL задан некорректно, пропускаю")
        return []

    try:
        print(f"📥 Загрузка серверов из {EXTERNAL_SOURCE_URL}...")
        with urllib.request.urlopen(EXTERNAL_SOURCE_URL, timeout=8) as response:
            return response.read().decode("utf-8").splitlines()
    except Exception:
        print("⚠️ Не удалось загрузить внешние серверы")
        return []


def normalize_base_link(link: str) -> str:
    return link.split("#", 1)[0].strip()


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return
    current_base = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            current_base = f.read().splitlines()

    external_servers = fetch_external_servers()

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    # Убираем дубли, но сохраняем порядок: сначала локальные, потом внешние
    all_lines = current_base + external_servers
    unique_lines = list(dict.fromkeys(line.strip() for line in all_lines if line.strip()))

    working_links = []
    seen_configs = set()
    counter = 1 
    working_for_base = []
    working_for_sub = []
    seen_base_links = set()
    counter = 1

    print(f"Начинаю проверку и нумерацию {len(lines)} строк...")
    print(f"Начинаю проверку {len(unique_lines)} уникальных строк...")

    for link in lines:
        link = link.strip()
        if not link.startswith('vless://') or link in seen_configs:
    for link in unique_lines:
        if not link.startswith("vless://"):
            continue
            
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            if check_server_smart(host, port):
                # ЛОГИКА НУМЕРАЦИИ:
                # Отрезаем всё после # и ставим свое имя wifi N
                base_part = link.split('#')[0]
                new_name = urllib.parse.quote(f"wifi {counter}")
                final_link = f"{base_part}#{new_name}"
                
                working_links.append(final_link)
                seen_configs.add(link)
                print(f"✅ ОК: {host} -> wifi {counter}")
                counter += 1

        base_part = normalize_base_link(link)
        if base_part in seen_base_links:
            continue

        host, port = extract_host_port(base_part)
        if not host or not port:
            continue

        if check_server_smart(host, port):
            working_for_base.append(base_part)
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{base_part}#{new_name}")
            seen_base_links.add(base_part)
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1

    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(HEADER + '\n'.join(working_links))
    
    print(f"Завершено. Сохранено в подписку: {len(working_links)}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово! База очищена. В подписке {len(working_for_sub)} серверов.")


if __name__ == "__main__":
    main()
