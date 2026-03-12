import socket, time, os, ssl, re, json

# Те же настройки путей
PINNED_FILE = 'test1/pinned.txt'
RANK_FILE = 'test1/ranking.json'
VETTED_FILE = 'test1/vetted.txt'
THRESHOLD = 50  # Сколько баллов в Мониторе должен набрать сервер для начала пыток
HOST_PORT_RE = re.compile(
    r'@(?P<host>[A-Za-z0-9.-]+):(?P<port>\d+)'  # только домены/IPv4, без []
)

def extract_host_port(link: str) -> tuple[str | None, int | None]:
    m = HOST_PORT_RE.search(link)
    if not m:
        return None, None

    host = m.group("host")
    port_str = m.group("port")

    # Отбрасываем то, что похоже на IPv6 (на всякий случай)
    if ":" in host or "[" in host or "]" in host:
        return None, None

    try:
        port = int(port_str)
    except ValueError:
        return None, None

    # Строгая проверка диапазона порта
    if not (1 <= port <= 65535):
        return None, None

    return host, port

def build_tls_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def torture_check(link):
    host, port = extract_host_port(link)
    if not host or not port:
        return False

    is_tls = "security=tls" in link.lower() or "security=reality" in link.lower()
    sni = re.search(r"sni=([^&?#]+)", link)
    server_hostname = sni.group(1) if sni else host

    # Увеличиваем до 20 попыток. 
    # При паузе в 60 сек один сервер будет проверяться ~20 минут.
    total_attempts = 20 
    
    for i in range(total_attempts):
        try:
            # Увеличиваем таймаут до 7 сек, чтобы не резать за секундный лаг
            with socket.create_connection((host, port), timeout=7) as s:
                if is_tls:
                    ctx = build_tls_context()
                    with ctx.wrap_socket(s, server_hostname=server_hostname):
                        pass
                else:
                    # Посылаем байтики начала SOCKS5
                    s.sendall(b'\x05\x01\x00')
                    # Даем серверу 2 секунды на ответ
                    s.settimeout(2)
                    try:
                        resp = s.recv(2)
                        if not resp:
                            raise Exception("Пустой ответ (шифрование/прокси не подтверждены)")
                    except socket.timeout:
                        # Некоторые прокси молчат, пока не придет полный запрос.
                        # Это нормально, но если хочешь жесткости — можно бросать ошибку здесь.
                        pass

            # Выводим прогресс, чтобы логи GitHub не выглядели мертвыми
            if (i + 1) % 5 == 0:
                print(f"   ⛓️  Прогресс пытки: {i + 1}/{total_attempts} пройден")

            # ПАУЗА — ГЛАВНЫЙ ИНСТРУМЕНТ. 
            # 60 секунд между попытками заставит бота мучать сервер 20 минут.
            time.sleep(60) 

        except Exception as e:
            print(f"❌ [ПРОВАЛ НА {i+1} ПОПЫТКЕ] Ошибка: {e}")
            return False

    return True
  
def load_ranking():
    if not os.path.exists(RANK_FILE): return {}
    try:
        with open(RANK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

def load_vetted():
    if not os.path.exists(VETTED_FILE): return set()
    with open(VETTED_FILE, 'r', encoding='utf-8') as f:
        # Берем только базу (до решетки), чтобы сравнивать уникальность
        return {line.split('#')[0].strip() for line in f if 'vless://' in line}

def process_pin_commands(token, repo, vetted_list):
    """Смотрит галочки и переносит из vetted в pinned"""
    if not token or not repo: return vetted_list
    try:
        # Читаем Issue с галочками
        cmd = ['gh', 'issue', 'list', '--repo', repo, '--label', 'pin_control', '--json', 'body', '--limit', '1']
        pin_read = subprocess.check_output(cmd, env={**os.environ, "GH_TOKEN": token}).decode()
        
        if pin_read and pin_read != "[]":
            issue_pin = json.loads(pin_read)[0]
            # Твоя регулярка (берет до решетки)
            to_pin = re.findall(r'- \[x\] (vless://[^\s#\s]+)', issue_pin['body'])
            
            if to_pin:
                added_bases = set()
                # Читаем, что уже есть в закрепах, чтобы не дублировать
                current_p = []
                if os.path.exists(PINNED_FILE):
                    with open(PINNED_FILE, 'r', encoding='utf-8') as f:
                        current_p = [l.strip() for l in f]

                # Записываем новые закрепы
                with open(PINNED_FILE, 'a', encoding='utf-8') as pf:
                    for s in to_pin:
                        base = s.strip()
                        if all(base != p.split("#")[0].strip() for p in current_p):
                            pf.write(base + "\n")
                            added_bases.add(base)
                            print(f"📌 Перенесено в pinned: {base}")

                # Если были переносы — чистим vetted_list
                if added_bases:
                    new_vetted = [v for v in vetted_list if v.split("#")[0].strip() not in added_bases]
                    # Перезаписываем файл vetted.txt
                    with open(VETTED_FILE, 'w', encoding='utf-8') as vf:
                        vf.write("\n".join(new_vetted) + ("\n" if new_vetted else ""))
                    return new_vetted
    except Exception as e:
        print(f"⚠️ Ошибка PIN: {e}")
    return vetted_list

def main_torturer():
    # --- ШАГ 0: ПОДГОТОВКА (ТОКЕН И РЕПО) ---
    token = os.getenv("GH_TOKEN")
    repo = os.getenv("GH_REPO")
    BLACKLIST_FILE = 'test1/blacklist.txt'

    if not os.path.exists(RANK_FILE):
        print("📭 Рейтинг пуст, пытать некого.")
        return

    ranking_db = load_ranking()
    
    # --- 1. ЗАГРУЗКА ВСЕХ СПИСКОВ-ИСКЛЮЧЕНИЙ ---
    # Читаем Vetted + обрабатываем перенос в Pinned
    if os.path.exists(VETTED_FILE):
        with open(VETTED_FILE, 'r', encoding='utf-8') as f:
            vetted_list = [l.strip() for l in f if 'vless://' in l]
    else: vetted_list = []

    vetted_list = process_pin_commands(token, repo, vetted_list)
    vetted_set = {v.split('#')[0].strip() for v in vetted_list}

    # Читаем Pinned (Закрепы)
    pinned_set = set()
    if os.path.exists(PINNED_FILE):
        with open(PINNED_FILE, 'r', encoding='utf-8') as f:
            pinned_set = {l.split('#')[0].strip() for l in f if 'vless://' in l}

    # Читаем Blacklist (Бан-лист)
    black_set = set()
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
            black_set = {l.split('#')[0].strip() for l in f if 'vless://' in l}

    # --- 2. УМНЫЙ ОТБОР КАНДИДАТОВ ---
    candidates = []
    for base, data in ranking_db.items():
        rank = data.get("rank", 0) if isinstance(data, dict) else data
        link = data.get("link", base) if isinstance(data, dict) else base

        if rank >= THRESHOLD:
            # Если сервер уже где-то есть (Vetted, Pinned или Blacklist)
            if base in vetted_set or base in pinned_set or base in black_set:
                # Обнуляем ранг, чтобы больше не проверялся как кандидат
                if isinstance(data, dict) and data.get("rank", 0) > 0:
                    ranking_db[base]['rank'] = 0
                continue
            
            candidates.append((base, link))

    if not candidates:
        print(f"⌛ Пока нет кандидатов с баллом >= {THRESHOLD}...")
        # Не делаем return сразу, так как нужно сохранить ranking_db, если были переносы
    else:
        print(f"🔥 Инквизиция начинается! На проверке {len(candidates)} кандидатов.")

        for base, full_link in candidates:
            print(f"⛓️ Пытаем {base[:30]}...")
            
            if torture_check(full_link):
                with open(VETTED_FILE, 'a', encoding='utf-8') as f:
                    f.write(full_link + "\n")
                
                if isinstance(ranking_db.get(base), dict):
                    ranking_db[base]['rank'] = 0 
                print(f"🎖️ СЕРВЕР ПРОШЕЛ ПЫТКИ: Повышен до VETTED!")
            else:
                if isinstance(ranking_db.get(base), dict):
                    ranking_db[base]['rank'] = max(0, ranking_db[base]['rank'] - 30)
                print(f"❌ СЛОМАЛСЯ НА ПЫТКАХ. Штраф -30 баллов.")

    # Сохраняем итоги (включая сброшенные баллы или результаты пыток)
    with open(RANK_FILE, 'w', encoding='utf-8') as f:
        json.dump(ranking_db, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main_torturer()
