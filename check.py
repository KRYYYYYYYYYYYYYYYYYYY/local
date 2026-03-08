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

# НОВАЯ НАСТРОЙКА: Внешний репозиторий
EXTERNAL_SOURCE_URL = "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt"

HEADER = """# profile-title: 🏴WIFI🏴
# announce: wifi
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def is_ipv6(host: str) -> bool:
    return ":" in host

def get_country_code(host: str) -> str:
    # Исправил тут небольшую опечатку в URL для API из твоего текста, чтобы работало
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
    match = re.search(r"@([\w.-]+):(\d+)", link)
    if match: return match.group(1), match.group(2)
    if match:
        return match.group(0), match.group(1), match.group(2)
    ipv6_match = re.search(r"@\[([0-9a-fA-F:]+)\]:(\d+)", link)
    if ipv6_match: return ipv6_match.group(1), ipv6_match.group(2)
    return None, None
    if ipv6_match:
        return ipv6_match.group(0), ipv6_match.group(1), ipv6_match.group(2)
    return None, None, None


def format_uri_host(host: str) -> str:
    if is_ipv6(host) and not host.startswith("["):
        return f"[{host}]"
    return host

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

# НОВАЯ ФУНКЦИЯ
def fetch_external_servers() -> list:
    """Скачивает серверы из внешнего источника."""
    if not EXTERNAL_SOURCE_URL:
        return []
    try:
        print(f"📥 Загрузка серверов из {EXTERNAL_SOURCE_URL}")
        with urllib.request.urlopen(EXTERNAL_SOURCE_URL, timeout=10) as response:
            return response.read().decode("utf-8").splitlines()
    except Exception as e:
        print(f"⚠️ Ошибка загрузки внешних серверов: {e}")
        return []

def main():
    # 1. Загрузка локальной базы
    local_lines = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            local_lines = f.read().splitlines()

    # 2. ПОДТЯЖКА ИЗ ВНЕШНЕГО РЕПО (Новое)
    external_lines = fetch_external_servers()
    
    # 3. ОБЪЕДИНЕНИЕ (Новое)
    combined_lines = local_lines + external_lines
    
    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = {}

    # Используем объединенный список combined_lines вместо current_base
    unique_links = list(dict.fromkeys(line.strip() for line in combined_lines if line.strip().startswith("vless://")))
    
    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1

    print(f"Начинаю проверку {len(unique_links)} строк...")

for link in unique_links:
        base_part = link.split("#", 1)[0].strip()
        host, port = extract_host_port(base_part)
        if not host or not port: continue
        endpoint, host, port = extract_host_port(base_part)
        if not endpoint or not host or not port: continue

        resolved_ip = None
        is_alive = False

        # Проверка страны и резолв
        if not is_ipv6(host):
            if get_country_code(host) not in BLOCKED_COUNTRIES:
                try:
                    resolved_ip = socket.gethostbyname(host)
                    with socket.create_connection((resolved_ip, int(port)), timeout=2.5):
                        is_alive = True
                except: pass
        else:
            # Для IPv6
            try:
                with socket.create_connection((host, int(port)), timeout=2.5):
                    is_alive = True
                    resolved_ip = host
            except: pass

        # Отрезаем старое имя для базы (до знака #)
        base_part = link.split("#", 1)[0]

        if is_alive:
            # Сервер ОК
            working_for_base.append(base_part)
            # HARD-RESOLVE: Заменяем домен на IP в ссылке для подписки
            sub_link = base_part.replace(f"@{host}:{port}", f"@{resolved_ip}:{port}")
            new_name = urllib.parse.quote(f"wifi {counter}")
            working_for_sub.append(f"{sub_link}#{new_name}")
            resolved_host = format_uri_host(resolved_ip)
            sub_link = link.replace(endpoint, f"@{resolved_host}:{port}", 1)
            working_for_sub.append(rebuild_link_name(sub_link, f"wifi {counter}"))
            counter += 1
            print(f"✅ ОК: {host} ({resolved_ip})")
        else:
            # Сервер упал - проверяем таймер
            fail_time = history.get(base_part, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_part)
                new_history[base_part] = fail_time
                new_name = urllib.parse.quote(f"wifi {counter} (DOWN)")
                working_for_sub.append(f"{base_part}#{new_name}")
                working_for_sub.append(rebuild_link_name(link, f"wifi {counter} (DOWN)"))
                counter += 1
                print(f"⏳ Ждем 48ч: {host}")
            else:
                print(f"🗑️ Удален мусор: {host}")
    
    # Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

if __name__ == "__main__":
    main()
