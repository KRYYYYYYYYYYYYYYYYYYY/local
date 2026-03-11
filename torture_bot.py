import socket, time, os, ssl, re, json

# Те же настройки путей
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

def main_torturer():
    if not os.path.exists(RANK_FILE):
        print("📭 Рейтинг пуст, пытать некого.")
        return

    ranking_db = load_ranking()
    vetted_set = load_vetted() 

    # Отбираем кандидатов
    candidates = []
    for base, data in ranking_db.items():
        # 1. Определяем ранг
        if isinstance(data, dict):
            rank = data.get("rank", 0)
            link = data.get("link", base) # Берем ссылку из словаря или саму базу
        else:
            rank = data  # Если там просто число
            link = base  # Если данных нет, сама ссылка и есть ключ (base)

        # 2. Проверяем порог
        if rank >= THRESHOLD and base not in vetted_set:
            candidates.append((base, link))

    if not candidates:
        print(f"⌛ Пока нет кандидатов с баллом >= {THRESHOLD}...")
        return

    print(f"🔥 Инквизиция начинается! На проверке {len(candidates)} кандидатов.")

    for base, full_link in candidates:
        print(f"⛓️ Пытаем {base[:30]}...")
        
        if torture_check(full_link):
            with open(VETTED_FILE, 'a', encoding='utf-8') as f:
                f.write(full_link + "\n")
            
            # ВАЖНО: После успеха сбрасываем балл, чтобы не пытать его завтра снова
            # Или вообще удаляем из рейтинга, т.к. он теперь в элите
            ranking_db[base]['rank'] = 0 
            print(f"🎖️ СЕРВЕР ПРОШЕЛ ПЫТКИ: Повышен до VETTED!")
        else:
            ranking_db[base]['rank'] = max(0, ranking_db[base]['rank'] - 30)
            print(f"❌ СЛОМАЛСЯ НА ПЫТКАХ. Штраф -30 баллов.")

    # Сохраняем итоги инквизиции
    with open(RANK_FILE, 'w', encoding='utf-8') as f:
        json.dump(ranking_db, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main_torturer()
