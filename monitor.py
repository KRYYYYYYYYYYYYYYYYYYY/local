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
    
    # --- УЛУЧШЕННЫЙ ИММУНИТЕТ ---
    if is_pinned(base_part): 
        # Если это закреп, мы возвращаем True, как будто он прошел все проверки идеально
        print(f"🛡️ [MONITOR] ЗАКРЕП ИГНОРИРУЕТСЯ: {base_part[:30]}...") 
        return True, 200 
    
    # Дальше идет обычная проверка для всех остальных...
    host, port = extract_host_port(base_part)

    if not host: return False, 404

    for _ in range(3): 
        try:
            start = time.time()
            with socket.create_connection((host, port), timeout=3.5) as s:
                if "security=tls" in link or "security=reality" in link:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    context.wrap_socket(s, server_hostname=host)
                else:
                    s.sendall(b'\x16\x03\x01\x00\x00')
            lat = (time.time() - start) * 1000
            if lat > 1000: return False, 1001 # Тормоз
            time.sleep(0.5)
        except: return False, 404 # Сдох
    return True, 200
    
def main_monitor():
    start_run = time.time()
    # Работаем 10 минут (лимит GitHub Actions), потом перезапуск
    while time.time() - start_run < 600:
        print(f"🕵️ Обход в {time.strftime('%H:%M:%S')}")
        
        if not os.path.exists(WIFI_FILE):
            time.sleep(60)
            continue

        with open(WIFI_FILE, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if 'vless://' in l]

        # Разделяем на закрепы и обычные
        pinned_in_wifi = [l for l in lines if is_pinned(l.split("#")[0].strip())]
        others_in_wifi = [l for l in lines if not is_pinned(l.split("#")[0].strip())]

        # ОГРАНИЧЕНИЕ: Берем только первые 50 закрепов, если их больше
        pinned_in_wifi = pinned_in_wifi[:50]
        
        # Проверяем только "Обычные" (others), закрепы внутри deep_kill_check и так имеют иммунитет
        valid_others = []
        for link in others_in_wifi:
            is_ok, status_code = deep_kill_check(link)
            if is_ok:
                valid_others.append(link)
            else:
                base = link.split("#")[0].strip()
                remove_from_all(base) # Удаляем из wifi и deferred
                if status_code == 404:
                    add_to_blacklist(base)
                    print(f"💀 БАН (Н/Д): {base[:30]}")
                elif status_code == 1001:
                    print(f"🐢 ТОРМОЗ (>1000ms): {base[:30]}")

        # ФОРМИРУЕМ ИТОГОВЫЙ СПИСОК (до 200 позиций суммарно)
        # Сначала наши 50 (или меньше) закрепов, потом остальные, сколько влезет до 200
        final_list = pinned_in_wifi + valid_others
        final_list = final_list[:200] 

        # Перезаписываем wifi.txt с сохранением хедера
        with open(WIFI_FILE, 'w', encoding='utf-8') as f:
            f.write("# profile-title: 🏴WIFI🏴\n\n" + "\n".join(final_list))
        
        print(f"📊 Мониторинг окончен: {len(pinned_in_wifi)} закрепов, {len(final_list) - len(pinned_in_wifi)} обычных.")
        time.sleep(60)

if __name__ == "__main__":
    main_monitor()
