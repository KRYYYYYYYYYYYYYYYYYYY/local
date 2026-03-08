import socket
import re
import os
import json
import urllib.request
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
# Настройки путей
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
GRACE_PERIOD = 2 * 24 * 60 * 60  # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Нумерованная, без IPv6 и RU/CN)
# announce: Hard-Resolve IP | SID и Reality Флаги Сохранены
# profile-update-interval: 2

"""

def is_ipv6(host):
    return ":" in host and not host.startswith('[')
BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}


def get_country_code(host):
def get_country_code(host: str) -> str:
    url = f"http://ip-api.com/json/{host}?fields=status,countryCode"
    try:
        # Исправлено: добавлен /json/ и правильный формат запроса
        url = f"http://ip-api.com{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                return data.get('countryCode')
    except:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    return "Unknown"

def check_server_smart(host, port):
    if is_ipv6(host):
        print(f"⏩ Пропуск IPv6: {host}")
        return False
    
    country = get_country_code(host)
    if country in ['RU', 'CN', 'IR', 'KP']:
        print(f"🚩 Пропуск {country} (No ChatGPT): {host}")
        return False

    try:
        ip_address = socket.gethostbyname(host)
        with socket.create_connection((ip_address, int(port)), timeout=2.5):
            return True
    except:
def extract_host_port(link: str) -> tuple[str | None, str | None, str | None]:
    """Возвращает full @host:port, host, port из vless-ссылки."""
    match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", link)
    if not match:
        return None, None, None

    original_host_port = match.group(0)
    host = match.group(1).strip("[]")
    port = match.group(2)
    return original_host_port, host, port


def should_block_host(host: str) -> bool:
    # IPv6 не фильтруем по стране (ip-api часто не дает корректный ответ по таким хостам)
    if ":" in host:
        return False
    return get_country_code(host) in BLOCKED_COUNTRIES


def make_subscription_link(base_link: str, original_host_port: str, resolved_ip: str, port: str, counter: int) -> str:
    """Собирает ссылку для подписки без потери существующего фрагмента (#...)."""
    target_host_port = f"@{resolved_ip}:{port}"
    resolved_link = base_link.replace(original_host_port, target_host_port, 1)

def main():
    # Если в ссылке уже есть '#', не добавляем вторую решетку и не трогаем существующий фрагмент.
    if "#" in resolved_link:
        return resolved_link

    new_name = urllib.parse.quote(f"wifi {counter}")
    return f"{resolved_link}#{new_name}"


def make_down_subscription_link(base_link: str, counter: int) -> str:
    # Если в ссылке уже есть '#', оставляем как есть (не ломаем флаг/frag).
    if "#" in base_link:
        return base_link

    new_name = urllib.parse.quote(f"wifi {counter} (DOWN)")
    return f"{base_link}#{new_name}"


def main() -> None:
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        current_base = file.read().splitlines()

    history: dict[str, float] = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as file:
                history = json.load(file)
        except (json.JSONDecodeError, OSError):
            history = {}

    unique_links = list(
        dict.fromkeys(line.strip() for line in current_base if line.strip().startswith("vless://"))
    )

    working_links = []
    seen_configs = set()
    counter = 1 
    working_for_base: list[str] = []
    working_for_sub: list[str] = []
    new_history: dict[str, float] = {}
    now = time.time()
    counter = 1

    print(f"Начинаю проверку и нумерацию {len(lines)} строк...")
    for link in unique_links:
        # Ключевое правило: НЕ режем ссылку по '#', чтобы не терять sid/флаги.
        base_link = link

    for link in lines:
        link = link.strip()
        if not link.startswith('vless://') or link in seen_configs:
        original_host_port, host, port = extract_host_port(base_link)
        if not original_host_port or not host or not port:
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

        if should_block_host(host):
            print(f"🚩 Пропуск по стране: {host}")
            continue

        resolved_ip = None
        is_alive = False

        if ":" not in host:
            try:
                resolved_ip = socket.gethostbyname(host)
                with socket.create_connection((resolved_ip, int(port)), timeout=2.5):
                    is_alive = True
            except (socket.gaierror, socket.timeout, OSError, ValueError):
                pass
        else:
            # IPv6 хост оставляем как есть, без hard-resolve.
            try:
                with socket.create_connection((host, int(port)), timeout=2.5):
                    is_alive = True
                    resolved_ip = host
            except (socket.gaierror, socket.timeout, OSError, ValueError):
                pass

        if is_alive and resolved_ip is not None:
            working_for_base.append(base_link)
            final_sub_link = make_subscription_link(
                base_link, original_host_port, resolved_ip, port, counter
            )
            working_for_sub.append(final_sub_link)
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            fail_time = history.get(base_link, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_link)
                new_history[base_link] = fail_time
                working_for_sub.append(make_down_subscription_link(base_link, counter))
                print(f"⏳ DOWN: {host}")
                counter += 1

    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as file:
        file.write("\n".join(working_for_base))

    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as file:
        json.dump(new_history, file, ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(HEADER + '\n'.join(working_links))
    
    print(f"Завершено. Сохранено в подписку: {len(working_links)}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(HEADER + "\n".join(working_for_sub))


if __name__ == "__main__":
    main()
