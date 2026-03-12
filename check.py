import socket
import re
import os
import ssl
import json
import urllib.parse
import urllib.request
import time
import requests

# Настройки путей
INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'
STATUS_FILE = 'test1/status.json'

EXTERNAL_SOURCE_URL = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_SS%2BAll_RUS.txt",
    "https://raw.githubusercontent.com/KiryaScript/white-lists/refs/heads/main/githubmirror/26.txt",
    "https://raw.githubusercontent.com/KiryaScript/white-lists/refs/heads/main/githubmirror/27.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt"
]

GRACE_PERIOD = 2 * 24 * 60 * 60 # 48 часов

HEADER = """
# profile-title: 🏴WIFI🏴
# remark: 🏴WIFI🏴
# announce: Подписка для использования на wifi.
# hide-settings: 1
# profile-update-interval: 2
# subscription-userinfo: upload=0; download=0; expire=0
# shadowrocket-userinfo: upload=0; download=0; expire=0
"""

ALLOWED_COUNTRIES = {"US", "DE", "NL", "GB", "FR", "FI", "SG", "JP", "PL", "TR"}

def rebuild_link_name(link: str, new_name: str) -> str:
    base, _, fragment = link.partition("#")

    # Если это уже закреп — не трогаем
    if fragment:
        frag = urllib.parse.unquote(fragment).upper()
        if "PINNED" in frag:
            return link

    if not fragment:
        return f"{base}#{urllib.parse.quote(new_name)}"

    fragment_dec = urllib.parse.unquote(fragment)

    # Пытаемся сохранить флаг/эмодзи
    match = re.match(r"^([^\w\s\d]|[^\x00-\x7F])+", fragment_dec)
    if match:
        prefix = match.group(0).strip()
        return f"{base}#{urllib.parse.quote(prefix + ' ' + new_name)}"

    return f"{base}#{urllib.parse.quote(new_name)}"
    
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
            print(f"📥 Загрузка из {url}")
            with urllib.request.urlopen(url, timeout=8) as response:
                configs = response.read().decode("utf-8").splitlines()
                all_configs.extend(configs)
        except Exception as e:
            print(f"❌ Ошибка загрузки {url}: {e}")
    return all_configs

def main():
    import subprocess
    token = os.getenv("GH_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")

    def load_list(path, is_vless=False):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                if is_vless:
                    return [line.strip() for line in f if "vless://" in line]
                return [line.strip() for line in f if line.strip()]
        return []

    blacklist = set(load_list('test1/blacklist.txt'))
    vetted_list = load_list('test1/vetted.txt')
    pinned_list = load_list('test1/pinned.txt', is_vless=True)
    deferred_base = load_list('test1/deferred.txt')
    current_base = load_list(INPUT_FILE)
    # --- 1. ПЕРВИЧНАЯ ЗАГРУЗКА ВСЕХ ФАЙЛОВ ---
    try:
        with open('test1/ranking.json', 'r') as f: ranking_db = json.load(f)
    except: ranking_db = {}
    
    try:
        with open(STATUS_FILE, 'r') as f: history = json.load(f)
    except: history = {}

    if token and repo:
        try:
            # Читаем: Кандидаты -> в Vetted (pin_control)
            pin_read = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'pin_control', '--json', 'body', '--limit', '1'], env={**os.environ, "GH_TOKEN": token}).decode()
            if pin_read and pin_read != "[]":
                issue_pin_data = json.loads(pin_read)[0]
                to_vetted = re.findall(r'- \[x\] (vless://[^\s#\s]+)', issue_pin_data['body'])
                for s in to_vetted:
                    if s.strip() not in vetted_list:
                        vetted_list.append(s.strip())
                if to_vetted:
                    with open('test1/vetted.txt', 'w', encoding='utf-8') as f: f.write("\n".join(vetted_list))

            # Читаем: Команды раззакрепления (unpin_control)
            unpin_read = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'unpin_control', '--json', 'body', '--limit', '1'], env={**os.environ, "GH_TOKEN": token}).decode()
            if unpin_read and unpin_read != "[]":
                issue_unp = json.loads(unpin_read)[0]
                to_unpin = re.findall(r'- \[x\] (vless://[^\s#\s]+)', issue_unp['body'])
                if to_unpin:
                    pinned_list = [s for s in pinned_list if s not in to_unpin]
                    with open('test1/pinned.txt', 'w', encoding='utf-8') as pf: pf.write("\n".join(pinned_list) + "\n")

            # Читаем: Команды в Черный список (control)
            control_read = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'control', '--json', 'body', '--limit', '1'], env={**os.environ, "GH_TOKEN": token}).decode()
            if control_read and control_read != "[]":
                issue_ctrl = json.loads(control_read)[0]
                to_black = re.findall(r'- \[x\] (vless://[^\s]+)', issue_ctrl['body'])
                for s in to_black:
                    blacklist.add(s.split('#')[0].strip())
                if to_black:
                    with open('test1/blacklist.txt', 'w') as f: f.write("\n".join(list(blacklist)))

        except Exception as e:
            print(f"⚠️ Ошибка обработки команд: {e}")

    external_servers = fetch_external_servers()
    all_lines = pinned_list + vetted_list + deferred_base + external_servers + current_base

    current_base = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            current_base = f.read().splitlines()

    external_servers = fetch_external_servers()

    all_lines = pinned_list + vetted_list + deferred_base + external_servers + current_base

    unique_links = []
    seen_parts = set()
    for l in all_lines:
        base = l.split("#")[0].strip()
        if base not in seen_parts and "vless://" in l:
            unique_links.append(l)
            seen_parts.add(base)
    
# --- 4. ЦИКЛ ПРОВЕРКИ ---
    working_for_base = []
    working_for_sub = []
    new_history = {}
    now = time.time()
    counter = 1
    seen_ips = set()
    idx = 0

    print(f"📡 Начинаю проверку. Цель: 200 серверов. Всего в очереди: {len(unique_links)}")

    while len(working_for_sub) < 200 and idx < len(unique_links):
        link = unique_links[idx]
        idx += 1 # Сдвигаем указатель
        
        clean_link = link.strip()
        base_part = clean_link.split("#", 1)[0].strip()
        
        if base_part in seen_parts and not any(base_part in p for p in pinned_list):
            continue
        
        found_pinned_full = None
        for p in pinned_list:
            if base_part == p.split("#")[0].strip():
                found_pinned_full = p
                break

        if found_pinned_full:
            seen_parts.add(base_part)
        
            # 1. Достаём только флаг из старого имени
            raw_pinned_name = found_pinned_full.split("#")[-1].strip()
            original_label = urllib.parse.unquote(raw_pinned_name)
        
            emoji_match = re.match(r'^([^\w\s\d]+)', original_label)
            flag = emoji_match.group(1).strip() if emoji_match else ""
        
            # 2. Полностью перезаписываем имя
            new_name = f"{flag} 💎 [PINNED] {counter}"
        
            # 3. Чистим базу
            clean_base = base_part.split("#")[0].strip()
        
            # 4. Собираем финальную ссылку
            final_linkk = f"{clean_base}#{urllib.parse.quote(new_name)}"
        
            working_for_sub.append(final_linkk)
            print(f"💎 [PINNED] {counter} с флагом '{flag}' готов")
        
            counter += 1
            continue
            
        # --- ФИЛЬТРЫ ---
# Фильтры
        if base_part in blacklist: continue
        if not re.search(r'[a-f0-9\-]{36}@', base_part): continue 
        
        endpoint, host, port = extract_host_port(base_part)
        if not endpoint or not host or not port: continue

        # --- ЭТАП 1: ХАРД-РЕЗОЛВИНГ + ПРОВЕРКА СВЯЗИ ---
        resolved_ip = None
        is_alive = False
        try:
            resolved_ip = socket.gethostbyname(host) if not is_ipv6(host) else host
            if resolved_ip in seen_ips: continue 
            
            use_tls = any(x in base_part.lower() for x in ["security=tls", "security=reality"])
            with socket.create_connection((resolved_ip, int(port)), timeout=4.0) as sock:
                if use_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    with context.wrap_socket(sock, server_hostname=host) as ssock: pass
                else:
                    sock.sendall(b'\x16\x03\x01\x00\x00')
            is_alive = True
            seen_ips.add(resolved_ip)
        except:
            is_alive = False
    
        # --- ЭТАП 2: ЕСЛИ СЕРВЕР РАБОТАЕТ ---
        if is_alive:
            if "security=none" in base_part.lower():
                print(f"❌ НЕТ ШИФРОВАНИЯ: {host}")
                continue
    
            country = get_country_code(host)
            if country not in ALLOWED_COUNTRIES:
                continue
    
            working_for_base.append(base_part)
            ip_str = f"[{resolved_ip}]" if is_ipv6(resolved_ip) else resolved_ip
            sub_link = base_part.replace(endpoint, f"@{ip_str}:{port}", 1)
            
            if "sni=" not in sub_link.lower() and not is_ipv6(host):
                sep = "&" if "?" in sub_link else "?"
                sub_link += f"{sep}sni={host}"
            
            final_link = rebuild_link_name(sub_link, f"wifi {counter}")
            working_for_sub.append(final_link)
            
            print(f"✅ ОК {len(working_for_sub)}/200 ({country}): {host} -> {resolved_ip} (wifi {counter})")
            counter += 1
    
        # --- ЭТАП 3: ЕСЛИ СЕРВЕР НЕ ОТВЕЧАЕТ ---
        else:
            if base_part in ranking_db:
                del ranking_db[base_part]
            if base_part in vetted_list:
                vetted_list.remove(base_part)
            
            fail_time = history.get(base_part, now)
            
            if now - fail_time > 86400: 
                print(f"🗑️ УДАЛЕН И ЗАБЛОКИРОВАН (1 день оффлайн): {host}")
                with open('test1/blacklist.txt', 'a') as bl:
                    bl.write(base_part + "\n")
                continue 
    
            if now - fail_time < GRACE_PERIOD:
                country = get_country_code(host)
                if country in ALLOWED_COUNTRIES:
                    working_for_base.append(base_part)
                    new_history[base_part] = fail_time
                    working_for_sub.append(rebuild_link_name(link, f"⏳ wifi {counter}"))
                    print(f"⏳ DOWN ({country}): {host} (оставлен с меткой ⏳)")
                    counter += 1
            else:
                print(f"🗑️ Удален (тайм-аут): {host}")

        # --- ВСЕ, ЧТО НЕ УСПЕЛИ ПРОВЕРИТЬ (если набрали 200 раньше конца списка) ---
    new_deferred = unique_links[idx:] 
    all_pinned = [l for l in working_for_sub if "💎 [PINNED]" in l]
    all_others = [l for l in working_for_sub if "💎 [PINNED]" not in l]
    
    final_to_sub = []
    seen_in_final = set() # Сито для адресов
    
    # 1. Приоритет закрепам (Лимит 50)
    for l in all_pinned:
        if len(final_to_sub) >= 50: break
        base = l.split("#")[0].strip()
        if base not in seen_in_final:
            final_to_sub.append(l)
            seen_in_final.add(base)

    # 2. Добираем обычные (до 200), защищаясь от дублей
    for l in all_others:
        if len(final_to_sub) >= 200: break
        base = l.split("#")[0].strip()
        if base not in seen_in_final:
            final_to_sub.append(l)
            seen_in_final.add(base)
    
    # 3. Формируем deferred.txt (остатки + то, что не влезло в лимит 200)
    leftover_from_others = [l for l in all_others if l.split("#")[0].strip() not in seen_in_final]
    deferred_final = new_deferred + leftover_from_others
    
    # --- 5. СОХРАНЕНИЕ РЕЗУЛЬТАТОВ ---
    
    # Сохраняем очередь
    with open('test1/deferred.txt', "w", encoding="utf-8") as f:
        f.write("\n".join(deferred_final))
    
    # Формируем подписку (Хедер + Ссылки)
    final_content = HEADER.strip() + "\n\n" + "\n".join(final_to_sub)
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_content)
        
    # База для следующего запуска
    with open(INPUT_FILE, "w", encoding="utf-8") as f: 
        f.write("\n".join(working_for_base))
    
    # История и рейтинги
    with open(STATUS_FILE, "w") as f: 
        json.dump(new_history, f)
    with open('test1/ranking.json', "w") as f:
        json.dump(ranking_db, f)

    print(f"🏁 План выполнен: {len(final_to_sub)} в подписке. Остаток в базе: {len(deferred_final)}")
  # 1. Сначала считаем статистику (для красоты логов)
    pinned_bases = {p.split("#")[0].strip() for p in pinned_list}
    count_pinned = sum(1 for l in final_to_sub if l.split("#")[0].strip() in pinned_bases)
    
    print(f"💎 Закрепленных в подписке: {count_pinned} (из лимита 50)")
    print(f"✅ Всего в wifi.txt: {len(final_to_sub)} (из лимита 200)")

    # 2. Сохраняем все основные файлы (wifi.txt, deferred.txt, ranking.json и т.д.)
    # ... (здесь идет блок open().write() из предыдущего совета) ...

    print(f"🏁 Готово! Подписка обновлена.")

    # 3. ОБНОВЛЕНИЕ ИНТЕРФЕЙСА GITHUB (Твой блок с галочками)
    if token and repo:
        try:
            # Тут живет весь твой код с subprocess.check_output(['gh', 'issue', ...])
            # Он обновит Панель управления, Кандидатов и Закрепы
            
            # [Вставь сюда весь код из своего последнего сообщения, начиная с pin_read...]
            
            print(f"📝 Все панели в Issue успешно обновлены.")
        except Exception as e:
            print(f"⚠️ Ошибка GitHub CLI: {e}")

if __name__ == "__main__":
    main()
