import socket
import re
import os
import ssl
import json
import urllib.parse
import urllib.request
import time
import requests
import subprocess

# Настройки путей
INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
STATUS_FILE = 'test1/status.json'

EXTERNAL_SOURCE_URL = [
    "https://raw.githubusercontent.com/KiryaScript/white-lists/refs/heads/main/githubmirror/27.txt"
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
    blacklist = set()
    token = os.getenv("GH_TOKEN")
    
    # 1. Читаем существующий файл (если есть)
    if os.path.exists('test1/blacklist.txt'):
        with open('test1/blacklist.txt', 'r') as f:
            blacklist = {line.strip() for line in f if line.strip()}

    # 2. Проверяем галочки в GitHub Issue (если есть токен)
    if token:
        try:
            # Ищем Issue с меткой 'control'
            issue_data = subprocess.check_output(
                repo = os.getenv("GITHUB_REPOSITORY")
                ['gh', 'issue', 'list', '--repo', repo, '--label', 'control', '--json', 'body,number', '--limit', '1'],
                env={**os.environ, "GH_TOKEN": token},
                stderr=subprocess.DEVNULL
            ).decode()
            
            if issue_data and issue_data != "[]":
                issue = json.loads(issue_data)[0]
                # Находим все ссылки, помеченные [x]
                checked = re.findall(r'- \[x\] (vless://[^\s]+)', issue['body'])
                for s in checked:
                    clean_s = s.split('#')[0] # Берем только саму ссылку
                    blacklist.add(clean_s)
                
                # Сохраняем обновленный черный список в файл
                with open('test1/blacklist.txt', 'w') as f:
                    f.write("\n".join(list(blacklist)))
        except Exception as e:
            print(f"⚠️ Ошибка чтения галочек: {e}")
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

    print(f"🔄 Проверка {len(unique_links)} строк")
    
    seen_ips = set() # <--- ОБЯЗАТЕЛЬНО ДОБАВЬ ПЕРЕД FOR
    for link in unique_links:
        base_part = link.split("#", 1)[0].strip()
                # --- ПРОВЕРКА ЧЕРНОГО СПИСКА ---
        if base_part in blacklist:
            print(f"🚫 ЗАБЛОКИРОВАН ГАЛОЧКОЙ: {base_part[:40]}...")
            continue
        
        # --- ФУНКЦИЯ 1: ВАЛИДАЦИЯ UUID ---
        if not re.search(r'[a-f0-9\-]{36}@', base_part):
            continue # Пропускаем ключи без пароля

        endpoint, host, port = extract_host_port(base_part)
        if not endpoint or not host or not port:
            continue

        # --- ЭТАП 1: ПРОВЕРКА ПОРТА + TLS + ЗАДЕРЖКА ---
        resolved_ip = None
        is_alive = False
        latency = 9999
        
        try:
            resolved_ip = socket.gethostbyname(host) if not is_ipv6(host) else host
            
            # --- ФУНКЦИЯ 2: УДАЛЕНИЕ ДУБЛИКАТОВ ПО IP ---
            if resolved_ip in seen_ips:
                continue # Скипаем, если этот IP уже был проверен
            
            start_time = time.time()
            use_tls = "security=tls" in base_part.lower() or "security=reality" in base_part.lower()
            
            with socket.create_connection((resolved_ip, int(port)), timeout=4.0) as sock:
                if use_tls:
                    context = ssl.create_default_context()
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        pass
                else:
                    sock.sendall(b'\x16\x03\x01\x00\x00')
                
                is_alive = True
                latency = int((time.time() - start_time) * 1000)
                seen_ips.add(resolved_ip) # Помечаем IP как рабочий
        except:
            is_alive = False

        # --- ЭТАП 2 И 3: ТОЛЬКО ЕСЛИ ЖИВОЙ ---
        if is_alive:
            if "security=none" in base_part.lower():
                print(f"❌ НЕТ ШИФРОВАНИЯ: {host}")
                continue

            country = get_country_code(host)
            if country not in ALLOWED_COUNTRIES:
                continue

            working_for_base.append(base_part)
            ip_str = f"[{resolved_ip}]" if is_ipv6(resolved_ip) else resolved_ip
            sub_link = link.replace(endpoint, f"@{ip_str}:{port}", 1)
            # Добавил latency в название, чтобы было видно пинг
            final_link = rebuild_link_name(sub_link, f"wifi {counter} [{latency}ms]")
            working_for_sub.append(final_link)
            
            print(f"✅ ОК ({country}): {host} -> wifi {counter}")
            counter += 1

        else:
            # --- ФУНКЦИЯ 3: АВТООЧИСТКА МУСОРА (7 дней) ---
            fail_time = history.get(base_part, now)
            
            if now - fail_time > 604800: # 7 суток
                print(f"🗑️ УДАЛЕН (7 дней оффлайн): {host}")
                continue # Ссылка больше не попадет в 1.txt

            # ЛОГИКА GRACE PERIOD (твоя старая)
            if now - fail_time < GRACE_PERIOD:
                country = get_country_code(host)
                if country in ALLOWED_COUNTRIES:
                    working_for_base.append(base_part)
                    new_history[base_part] = fail_time
                    working_for_sub.append(rebuild_link_name(link, f"wifi {counter} (DOWN)"))
                    print(f"⏳ DOWN ({country}): {host}")
                    counter += 1
            else:
                print(f"🗑️ Удален (тайм-аут): {host}")

    # 3. Сохранение
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(working_for_base))
    with open(STATUS_FILE, "w") as f: json.dump(new_history, f)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(working_for_sub))

    print(f"🏁 Готово! Подписка обновлена.")
       # --- ОБНОВЛЕНИЕ ИНТЕРФЕЙСА С ГАЛОЧКАМИ ---
    if token:
        try:
            # Формируем текст: [ ] для рабочих, [x] для тех, кто уже в черном списке
            issue_body = "### Панель управления серверами\n"
            issue_body += "Отметь [x] и сохрани, чтобы отправить в черный список:\n\n"
            
            # Добавляем рабочие серверы
            for i, link in enumerate(working_for_base, 1):
                status = "[x]" if link in blacklist else "[ ]"
                issue_body += f"- {status} {link} (wifi {i})\n"

            with open("issue_body.txt", "w") as f: f.write(issue_body)
            
            # Редактируем Issue (метка control должна быть создана в репо заранее)
            subprocess.run(['gh', 'issue', 'edit', '--label', 'control', '--body-file', 'issue_body.txt'], 
                           env={**os.environ, "GH_TOKEN": token})
            print("📝 Список галочек в GitHub Issue обновлен.")
        except Exception as e:
            print(f"⚠️ Не удалось обновить Issue: {e}")

if __name__ == "__main__":
    main()
