import socket, time, os, ssl, re, json, subprocess

# Файлы
WIFI_FILE = 'kr/mob/wifi.txt'
DEFERRED_FILE = 'test1/deferred.txt'
INPUT_FILE = 'test1/1.txt'
BLACKLIST_FILE = 'test1/blacklist.txt'
PINNED_FILE = 'test1/pinned.txt'

def extract_host_port(link):
    match = re.search(r'@([\w\.-]+):(\d+)', link)
    if not match:
        match = re.search(r'@\[([0-9a-fA-F:]+)\]:(\d+)', link)
    return (match.group(1), int(match.group(2))) if match else (None, None)

def is_pinned(base_part):
    if not os.path.exists(PINNED_FILE): return False
    with open(PINNED_FILE, 'r', encoding='utf-8') as f:
        # Читаем файл и для каждой строки берем только часть до знака #
        pinned_bases = [line.split('#')[0].strip() for line in f if 'vless://' in line]
        return base_part in pinned_bases
        
def add_to_blacklist(base_part):
    existing = set()
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            existing = {line.strip() for line in f}
    if base_part not in existing:
        with open(BLACKLIST_FILE, 'a') as f:
            f.write(base_part + "\n")

def remove_from_all(base_part):
    # УБРАЛИ INPUT_FILE (1.txt), чтобы сервер остался в базе для перепроверки
    for path in [WIFI_FILE, DEFERRED_FILE]: 
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Оставляем только те строки, где НЕТ этого сервера
            new_lines = [l for l in lines if base_part not in l]
            
            if len(lines) != len(new_lines):
                with open(path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                print(f"🗑️ Временно удален из {path} (не прошел мониторинг)")

def deep_kill_check(link):
    base_part = link.split("#")[0].strip()
    
    # --- ИММУНИТЕТ ДЛЯ ЗАКРЕПОВ ---
    if is_pinned(base_part): 
        print(f"🛡️ [MONITOR] ЗАКРЕП ИГНОРИРУЕТСЯ: {base_part[:30]}...") 
        return True, 200 
    
    host, port = extract_host_port(base_part)
    if not host or not port: return False, 404

    # Пытаемся 3 раза, прежде чем вынести приговор
    for attempt in range(3): 
        try:
            start = time.time()
            # Увеличиваем таймаут на коннект до 4.5с, чтобы не резать "далекие" сервера
            with socket.create_connection((host, int(port)), timeout=4.5) as s:
                
                if "security=tls" in link.lower() or "security=reality" in link.lower():
                    # Пытаемся вытащить реальный SNI из ссылки
                    sni_match = re.search(r'sni=([^&?#]+)', link)
                    server_hostname = sni_match.group(1) if sni_match else host
                    
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    
                    # Полноценная проверка TLS-рукопожатия
                    with context.wrap_socket(s, server_hostname=server_hostname) as ssock:
                        pass
                else:
                    # Для обычных соединений шлем проверочный байт
                    s.sendall(b'\x05\x01\x00') 
            
            lat = (time.time() - start) * 1000
            
            # --- ПРОВЕРКА НА ТОРМОЗА ---
            # 1500мс — золотая середина. И не лагает, и не режет лишнего.
            if lat > 1500: 
                return False, 1001 
            
            # Если дошли сюда — сервер живой и быстрый
            return True, 200
            
        except (socket.timeout, ConnectionRefusedError, ssl.SSLError):
            # Если это была не последняя попытка — ждем чуть-чуть и пробуем снова
            if attempt < 2:
                time.sleep(0.5)
                continue
            return False, 404
        except Exception as e:
            return False, 404
            
    return False, 404
    
def main_monitor():
    start_run = time.time()
    
    # --- ЗАГРУЗКА РЕЙТИНГА ---
    ranking_db = {}
    RANK_FILE = 'test1/ranking.json'
    VETTED_FILE = 'test1/vetted.txt'
    
    if os.path.exists(RANK_FILE):
        try:
            with open(RANK_FILE, 'r', encoding='utf-8') as f:
                ranking_db = json.load(f)
        except: ranking_db = {}

    while time.time() - start_run < 600:
        print(f"🕵️ Обход в {time.strftime('%H:%M:%S')}")
        
        if not os.path.exists(WIFI_FILE):
            time.sleep(60)
            continue

        with open(WIFI_FILE, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if 'vless://' in l]

        pinned_in_wifi = [l for l in lines if is_pinned(l.split("#")[0].strip())]
        others_in_wifi = [l for l in lines if not is_pinned(l.split("#")[0].strip())]
        pinned_in_wifi = pinned_in_wifi[:50]
        
        valid_others = []
        for link in others_in_wifi:
            base = link.split("#")[0].strip()
            is_ok, status_code = deep_kill_check(link)
            
            if is_ok:
                valid_others.append(link)

                # --- БЕЗОПАСНОЕ ПОЛУЧЕНИЕ РАНГА ---
                old_data = ranking_db.get(base, 0)
                if isinstance(old_data, dict):
                    old_rank = old_data.get("rank", 0)
                else:
                    old_rank = old_data # Если там было просто число
                
                new_rank = old_rank + 1
                
                # --- СОХРАНЕНИЕ В ПРАВИЛЬНОМ ФОРМАТЕ ---
                ranking_db[base] = {"rank": new_rank, "link": link}
                
                print(f"📈 {base[:20]}... живет. Баллы: {new_rank}")
                
            else:
                # Если сервер упал — удаляем его из рейтинга совсем
                if base in ranking_db:
                    del ranking_db[base]
                remove_from_all(base)
                print(f"🧊 {base[:20]}... упал. Рейтинг обнулен.")
                
                if status_code == 404:
                    add_to_blacklist(base)
                    print(f"💀 БАН (Н/Д): {base[:30]}")
                elif status_code == 1001:
                    print(f"🐢 ТОРМОЗ (>1000ms): {base[:30]}")

        # Сохраняем прогресс рейтинга после каждого круга
        with open(RANK_FILE, 'w', encoding='utf-8') as f:
            json.dump(ranking_db, f, ensure_ascii=False, indent=4)

        final_list = pinned_in_wifi + valid_others
        final_list = final_list[:200] 

        with open(WIFI_FILE, 'w', encoding='utf-8') as f:
            f.write("# profile-title: 🏴WIFI🏴\n\n" + "\n".join(final_list))
        
        print(f"📊 Монитор: {len(pinned_in_wifi)} закрепов, {len(valid_others)} живых. Рейтинг обновлен.")
        time.sleep(60)

if __name__ == "__main__":
    main_monitor()
