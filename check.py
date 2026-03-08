import socket
import re
import os
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
import urllib.parse

INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
GRACE_PERIOD = 2 * 24 * 60 * 60

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Нумерованная, без IPv6 и RU/CN)
# announce: SID любой длины сохранен | Hard-Resolve IP
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
        return False
def extract_host_port(link: str) -> tuple[str | None, str | None, str | None]:
    match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", link)
    if not match:
        return None, None, None
    return match.group(0), match.group(1).strip("[]"), match.group(2)


def trim_to_sid_value(link: str) -> str:
    """
    Сохраняет ссылку до конца значения sid=... .
    Обрезает все, что идет после первого разделителя после sid:
    '+' или '%20' или '#' или пробел.
    """
    sid_pos = link.find("sid=")
    if sid_pos == -1:
        return re.split(r"[#+ ]", link, maxsplit=1)[0]

    scan_from = sid_pos + 4
    positions = []

    plus_pos = link.find("+", scan_from)
    if plus_pos != -1:
        positions.append(plus_pos)

    pct20_pos = link.find("%20", scan_from)
    if pct20_pos != -1:
        positions.append(pct20_pos)

    hash_pos = link.find("#", scan_from)
    if hash_pos != -1:
        positions.append(hash_pos)

def main():
    space_pos = link.find(" ", scan_from)
    if space_pos != -1:
        positions.append(space_pos)

    end_pos = min(positions) if positions else len(link)
    return link[:end_pos]


def main() -> None:
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        lines = file.read().splitlines()

    history: dict[str, float] = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as file:
                history = json.load(file)
        except (json.JSONDecodeError, OSError):
            history = {}

    working_links = []
    seen_configs = set()
    counter = 1 
    unique_links = list(dict.fromkeys(line.strip() for line in lines if line.strip().startswith("vless://")))

    print(f"Начинаю проверку и нумерацию {len(lines)} строк...")
    working_for_base: list[str] = []
    working_for_sub: list[str] = []
    new_history: dict[str, float] = {}
    now = time.time()
    counter = 1

    for link in unique_links:
        base_part = trim_to_sid_value(link)

        original_host_port, host, port = extract_host_port(base_part)
        if not original_host_port or not host or not port:
            continue

    for link in lines:
        link = link.strip()
        if not link.startswith('vless://') or link in seen_configs:
        if ":" not in host and get_country_code(host) in BLOCKED_COUNTRIES:
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

        resolved_ip = None
        is_alive = False

        try:
            resolved_ip = socket.gethostbyname(host) if ":" not in host else host
            with socket.create_connection((resolved_ip, int(port)), timeout=2.5):
                is_alive = True
        except (socket.gaierror, socket.timeout, OSError, ValueError):
            is_alive = False

        if is_alive and resolved_ip is not None:
            working_for_base.append(base_part)
            sub_link = base_part.replace(original_host_port, f"@{resolved_ip}:{port}", 1)
            working_for_sub.append(f"{sub_link}+wifi+{counter}")
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            fail_time = history.get(base_part, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(base_part)
                new_history[base_part] = fail_time
                working_for_sub.append(f"{base_part}+wifi+{counter}+(DOWN)")
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
