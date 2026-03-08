import socket
import re
import os
import json
import time
import urllib.parse
import urllib.request
import urllib.error

# Настройки путей
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
GRACE_PERIOD = 2 * 24 * 60 * 60  # 48 часов

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Hard-Resolve IP | SID и Reality Флаги Сохранены
# profile-update-interval: 2

"""

BLOCKED_COUNTRIES = {"RU", "CN", "IR", "KP"}

def get_country_code(host: str) -> str:
    url = f"http://ip-api.com/json/{host}?fields=status,countryCode"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "Unknown")
    except Exception:
        pass
    return "Unknown"

def extract_host_port(link: str):
    """Возвращает full @host:port, host, port из vless-ссылки."""
    match = re.search(r"@([\w\.-]+|\[[0-9a-fA-F:]+\]):(\d+)", link)
    if not match:
        return None, None, None
    return match.group(0), match.group(1).strip("[]"), match.group(2)

def make_subscription_link(base_link: str, original_hp: str, resolved_ip: str, port: str, counter: int) -> str:
    """Заменяет хост на IP и добавляет имя, только если его нет."""
    target_hp = f"@{resolved_ip}:{port}"
    new_link = base_link.replace(original_hp, target_hp, 1)
    if "#" in new_link:
        return new_link
    name = urllib.parse.quote(f"wifi {counter}")
    return f"{new_link}#{name}"

def make_down_link(base_link: str, counter: int) -> str:
    if "#" in base_link:
        return base_link
    name = urllib.parse.quote(f"wifi {counter} (DOWN)")
    return f"{base_link}#{name}"

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        current_base = f.read().splitlines()

    history = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    unique_links = list(dict.fromkeys(line.strip() for line in current_base if line.strip().startswith("vless://")))
    
    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1

    print(f"Начинаю проверку {len(unique_links)} строк...")

    for link in unique_links:
        orig_hp, host, port = extract_host_port(link)
        if not orig_hp:
            continue

        # Фильтр стран
        if ":" not in host and get_country_code(host) in BLOCKED_COUNTRIES:
            print(f"🚩 Пропуск (RU/CN): {host}")
            continue

        resolved_ip = None
        is_alive = False

        try:
            if ":" not in host:
                resolved_ip = socket.gethostbyname(host)
                check_ip = resolved_ip
            else:
                check_ip = host
                resolved_ip = host
            
            with socket.create_connection((check_ip, int(port)), timeout=2.5):
                is_alive = True
        except Exception:
            is_alive = False

        if is_alive:
            working_for_base.append(link)
            working_for_sub.append(make_subscription_link(link, orig_hp, resolved_ip, port, counter))
            print(f"✅ ОК: {host} -> wifi {counter}")
            counter += 1
        else:
            fail_time = history.get(link, now)
            if now - fail_time < GRACE_PERIOD:
                working_for_base.append(link)
                new_history[link] = fail_time
                working_for_sub.append(make_down_link(link, counter))
                print(f"⏳ DOWN: {host}")
                counter += 1
            else:
                print(f"🗑️ Удален: {host}")

    # Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(working_for_base))

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово. В подписке: {len(working_for_sub)}")

if __name__ == "__main__":
    main()
