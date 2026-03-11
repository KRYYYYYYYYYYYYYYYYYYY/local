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

HEADER = """# profile-title: 🏴WIFI🏴
# remark: 🏴WIFI🏴
# announce: Подписка для использования на wifi.
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

    blacklist = set()
    pinned_list = []
    deferred_base = []
    current_base = []
    external_servers = []
    ranking_db = {}
    vetted_list = []
    
    blacklist = set()
    if os.path.exists('test1/blacklist.txt'):
        with open('test1/blacklist.txt', 'r') as f:
            blacklist = {line.strip() for line in f if line.strip()}

        # Загружаем "рейтинг выслуги"
    ranking_file = 'test1/ranking.json'
    ranking_db = {}
    if os.path.exists(ranking_file):
        try:
            with open(ranking_file, "r") as f: ranking_db = json.load(f)
        except: ranking_db = {}

    # Загружаем текущих проверенных (чтобы не дублировать)
    vetted_list = []
    if os.path.exists('test1/vetted.txt'):
        with open('test1/vetted.txt', 'r') as f:
            vetted_list = [line.strip() for line in f if line.strip()]


    # --- ДОБАВЛЯЕМ ЗАГРУЗКУ СПЕЦФАЙЛОВ ТУТ ---
    
    # 1. Загружаем Закрепленные (Pinned)
    pinned_list = []
    if os.path.exists('test1/pinned.txt'):
        with open('test1/pinned.txt', 'r', encoding='utf-8') as f:
            # Читаем всё целиком, убираем пустые строки
            pinned_list = [line.strip() for line in f if "vless://" in line]
    
    print(f"📦 Загружено закрепов из файла: {len(pinned_list)}")

    clean_pinned = {}
    for p in pinned_list:
        base = p.split("#")[0].strip()
        clean_pinned[base] = p  # последний вариант перезапишет предыдущий

    pinned_list = list(clean_pinned.values())

    # 2. Загружаем Отложенные (Deferred)
    deferred_base = []
    if os.path.exists('test1/deferred.txt'):
        with open('test1/deferred.txt', 'r', encoding='utf-8') as f:
            deferred_base = [line.strip() for line in f if line.strip()]

    # ------------------------------------------

    # Дальше твоя стандартная загрузка
    current_base = []
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            current_base = f.read().splitlines()

    external_servers = fetch_external_servers()
    
    # СОБИРАЕМ ОЧЕРЕДЬ: База + Отложенные + Новые
    # Это гарантирует, что "старички" из очереди проверятся раньше новичков
    all_lines = current_base + deferred_base + external_servers

    # 2. Проверяем галочки в GitHub Issue (если есть токен)
    if token and repo: # Добавь проверку и на токен, и на репо
        try:
            # Ищем Issue с меткой 'control'
            cmd = ['gh', 'issue', 'list', '--repo', repo, '--label', 'control', '--json', 'body,number', '--limit', '1']
            issue_data = subprocess.check_output(
                cmd, 
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

            pin_read = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'pin_control', '--json', 'body', '--limit', '1'], env={**os.environ, "GH_TOKEN": token}).decode()
            if pin_read and pin_read != "[]":
                issue_pin = json.loads(pin_read)[0]
                to_pin = re.findall(r'- \[x\] (vless://[^\s#\s]+)', issue_pin['body'])
                if to_pin:
                    with open('test1/pinned.txt', 'a', encoding='utf-8') as pf:
                        for s in to_pin:
                            base = s.split("#")[0].strip()
                            if all(base != p.split("#")[0].strip() for p in pinned_list):
                                pf.write(s.strip() + "\n")
                                pinned_list.append(s.strip())

            # ЧИТАЕМ ГАЛОЧКИ ДЛЯ РАЗЗАКРЕПЛЕНИЯ (unpin_control)
            unpin_read = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'unpin_control', '--json', 'body', '--limit', '1'], env={**os.environ, "GH_TOKEN": token}).decode()
            if unpin_read and unpin_read != "[]":
                issue_unp = json.loads(unpin_read)[0]
                to_unpin = re.findall(r'- \[x\] (vless://[^\s#\s]+)', issue_unp['body'])
                if to_unpin:
                    pinned_list = [s for s in pinned_list if s not in to_unpin]
                    with open('test1/pinned.txt', 'w', encoding='utf-8') as pf:
                        pf.write("\n".join(pinned_list) + "\n")
        except Exception as e:
            print(f"⚠️ Ошибка чтения команд: {e}")

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

# --- ИЗМЕНЕНИЕ ТУТ: МЕНЯЕМ ПОРЯДОК ОЧЕРЕДИ ---
    # Сначала отложенные с прошлого раза, потом новые, потом старые из базы
    all_lines = pinned_list + deferred_base + external_servers + current_base
    
    # Убираем дубликаты, сохраняя этот новый приоритетный порядок
    unique_links = []
    seen_parts = set()
    for l in all_lines:
        base = l.split("#")[0].strip()
        if base not in seen_parts and "vless://" in l:
            unique_links.append(l)
            seen_parts.add(base)
    
    working_for_base = []
    working_for_sub = []
    new_deferred = []   # <--- ДОБАВЬ ЭТО (сюда пойдут те, кто не влез в лимит)
    new_history = {}
    now = time.time()
    counter = 1
    checked_today = 0   # <--- ДОБАВЬ ЭТО (счетчик реальных проверок)
    MAX_TO_CHECK = 300  # <--- ДОБАВЬ ЭТО (лимит, чтобы скрипт не шел до конца очереди вечно)
    seen_ips = set()
    # ----------------------------------------------------------
# --- ЦИКЛ ПРОВЕРКИ (ИЩЕМ 200 РАБОЧИХ) ---
    print(f"📡 Начинаю проверку. Цель: 200 серверов. Всего в очереди: {len(unique_links)}")
    
    seen_parts = set()
    
    idx = 0
    # Работаем, пока не набрали 200 в подписку ИЛИ пока не кончились ссылки в unique_links
    while len(working_for_sub) < 200 and idx < len(unique_links):
        link = unique_links[idx]
        idx += 1 # Сдвигаем указатель
        
        clean_link = link.strip()
        base_part = clean_link.split("#", 1)[0].strip()
        
        if base_part in seen_parts and not any(base_part in p for p in pinned_list):
            continue
        
        # --- БЛОК ЗАКРЕПОВ (PINNED) ---
        # --- БЛОК ЗАКРЕПОВ (PINNED) ---
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
        if base_part in blacklist:
            continue
        if not re.search(r'[a-f0-9\-]{36}@', base_part):
            continue 
    
        endpoint, host, port = extract_host_port(base_part)
        if not endpoint or not host or not port:
            continue

        # --- ЭТАП 1: ХАРД-РЕЗОЛВИНГ + ПРОВЕРКА СВЯЗИ ---
        resolved_ip = None
        is_alive = False
        try:
            resolved_ip = socket.gethostbyname(host) if not is_ipv6(host) else host
            if resolved_ip in seen_ips:
                continue 
            
            start_time = time.time()
            use_tls = "security=tls" in base_part.lower() or "security=reality" in base_part.lower()
            
            with socket.create_connection((resolved_ip, int(port)), timeout=4.0) as sock:
                if use_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        pass
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
    # --- КОНЕЦ ЦИКЛА ПРОВЕРКИ ---
    # --- ЛОГИКА ОЧЕРЕДИ И ЛИМИТОВ (ИСПРАВЛЕНО) ---
        
     #   1. Разделяем то, что нашли, на две кучи
    all_pinned = [l for l in working_for_sub if "💎 [PINNED]" in l]
    all_others = [l for l in working_for_sub if "💎 [PINNED]" not in l]
    
    final_to_sub = []
    seen_in_final = set()# То самое "сито" для адресов
    
    # 2. Сначала берем закрепы (Приоритет №1)
    # Лимит 50 штук
    for l in all_pinned:
        if len(final_to_sub) >= 50: break
        base = l.split("#")[0].strip()
        if base not in seen_in_final:
            final_to_sub.append(l)
            seen_in_final.add(base)
    # 3. Добираем обычные сервера, пока не станет 200 (Приоритет №2)
    # Но только те, которых еще НЕТ в закрепах
    for l in all_others:
        if len(final_to_sub) >= 200: break
        base = l.split("#")[0].strip()
        if base not in seen_in_final: # ВОТ ОНА — ЗАЩИТА ОТ ДУБЛЯ
            final_to_sub.append(l)
            seen_in_final.add(base)
    
    # 4. Формируем deferred.txt (остатки)
    # Сюда идет то, что не влезло + то, что вообще не проверялось 
    leftover_from_others = [l for l in all_others if l.split("#")[0].strip() not in seen_in_final]
    deferred_final = new_deferred + leftover_from_others
    
# 5. Сохраняем результат
    
    # Сначала сохраняем deferred.txt (очередь на потом)
    with open('test1/deferred.txt', "w", encoding="utf-8") as f:
        f.write("\n".join(deferred_final))
    
    # ФОРМИРУЕМ ПРАВИЛЬНЫЙ ТЕКСТ ДЛЯ ПОДПИСКИ
    # .strip() убирает случайные пробелы в начале/конце хедера
    # \n\n гарантирует, что между командами и ссылками будет пустая строка (важно для iPhone)
    final_content = HEADER.strip() + "\n\n" + "\n".join(final_to_sub)

    # ЗАПИСЫВАЕМ В ОСНОВНОЙ ФАЙЛ (kr/mob/wifi.txt)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_content)
        
    # Сохраняем рабочую базу ссылок для следующего запуска чекера
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f: 
        f.write("\n".join(working_for_base))
    
    # Сохраняем историю и рейтинги
    with open(STATUS_FILE, "w") as f: 
        json.dump(new_history, f)
    with open('test1/ranking.json', "w") as f:
        json.dump(ranking_db, f)

    print(f"🏁 План выполнен: {len(final_to_sub)} в подписке. Остаток в базе: {len(deferred_final)}")
    # Базовые части закрепов
    pinned_bases = {p.split("#")[0].strip() for p in pinned_list}
    
    # Сколько закрепов реально попало в подписку
    count_pinned = sum(
        1 for l in final_to_sub
        if l.split("#")[0].strip() in pinned_bases
    )
    
    print(f"💎 Закрепленных в подписке: {count_pinned} (из лимита 50)")
    print(f"✅ Всего в wifi.txt: {len(final_to_sub)} (из лимита 200)")
    
    # 3. Сохранение (ТВОЙ БЛОК БЕЗ ИЗМЕНЕНИЙ НАДПИСЕЙ)
    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w", encoding="utf-8") as f: 
        f.write("\n".join(working_for_base))
    
    with open(STATUS_FILE, "w") as f: 
        json.dump(new_history, f)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # ЗАМЕНИ ТУТ working_for_sub на final_to_sub
        f.write(HEADER + "\n".join(final_to_sub))

    print(f"🏁 Готово! Подписка обновлена.")
    # --- ОБНОВЛЕНИЕ ИНТЕРФЕЙСА С ГАЛОЧКАМИ ---
    if token and repo:  # Теперь repo точно определена
        try:
            # Получаем текущее время
            update_time = time.strftime("%d.%m.%Y %H:%M:%S")
            
            issue_body = f"### 🎮 Панель управления серверами\n"
            issue_body += f"🕒 **Последнее обновление:** `{update_time}`\n\n"
            issue_body += "Отметь [x] и сохрани, чтобы отправить в черный список:\n\n---\n\n"

            find_cmd = ['gh', 'issue', 'list', '--repo', repo, '--label', 'control', '--json', 'number', '--limit', '1']
            out = subprocess.check_output(find_cmd, env={**os.environ, "GH_TOKEN": token}).decode()
            
            if out and out != "[]":
                issue_number = str(json.loads(out)[0]['number'])
                for i, link in enumerate(working_for_base, 1):
                    status = "[x]" if link in blacklist else "[ ]"
                    issue_body += f"- {status} {link} (wifi {i})\n\n"
                    issue_body += "---\n\n"
                
                with open("issue_body.txt", "w", encoding="utf-8") as f: 
                    f.write(issue_body)
                
                subprocess.run(['gh', 'issue', 'edit', issue_number, '--repo', repo, '--body-file', 'issue_body.txt'], 
                               env={**os.environ, "GH_TOKEN": token})
                print(f"📝 Список галочек в Issue #{issue_number} обновлен.")

            # --- ПАНЕЛЬ 2: КАНДИДАТЫ В ЗАКРЕП (PIN) ---
            pin_cmd = ['gh', 'issue', 'list', '--repo', repo, '--label', 'pin_control', '--json', 'number', '--limit', '1']
            out_pin = subprocess.check_output(pin_cmd, env={**os.environ, "GH_TOKEN": token}).decode()
            if out_pin and out_pin != "[]":
                num_pin = str(json.loads(out_pin)[0]['number'])
                body_pin = f"### 💎 Кандидаты в закреп\n🕒 Обновлено: `{update_time}`\n\n"
                for i, link in enumerate(vetted_list, 1):
                    if link not in pinned_list:
                        body_pin += f"- [ ] {link} (wifi {i})\n\n---\n\n"
                with open("pin_body.txt", "w", encoding="utf-8") as f: 
                    f.write(body_pin)
                subprocess.run(['gh', 'issue', 'edit', num_pin, '--repo', repo, '--body-file', 'pin_body.txt'], 
                               env={**os.environ, "GH_TOKEN": token})

            # --- ПАНЕЛЬ 3: УПРАВЛЕНИЕ ЗАКРЕПАМИ (UNPIN) ---
            unpin_cmd = ['gh', 'issue', 'list', '--repo', repo, '--label', 'unpin_control', '--json', 'number', '--limit', '1']
            out_unp = subprocess.check_output(unpin_cmd, env={**os.environ, "GH_TOKEN": token}).decode()
            if out_unp and out_unp != "[]":
                num_unp = str(json.loads(out_unp)[0]['number'])
                body_unp = f"### 👑 Ваши закрепленные сервера\n🕒 Обновлено: `{update_time}`\n\n"
                for i, link in enumerate(pinned_list, 1):
                    body_unp += f"- [ ] {link} (FIXED {i})\n\n---\n\n"
                with open("unpin_body.txt", "w", encoding="utf-8") as f: 
                    f.write(body_unp)
                subprocess.run(['gh', 'issue', 'edit', num_unp, '--repo', repo, '--body-file', 'unpin_body.txt'], 
                               env={**os.environ, "GH_TOKEN": token})
            with open('test1/ranking.json', "w") as f:
                json.dump(ranking_db, f)

        except Exception as e:
            print(f"⚠️ Не удалось обновить Issue: {e}")

if __name__ == "__main__":
    main()
