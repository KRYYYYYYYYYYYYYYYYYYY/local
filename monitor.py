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
    while time.time() - start_run < 600:
        print(f"🕵️ Обход в {time.strftime('%H:%M:%S')}")
        
        all_to_check = []
        for f in [WIFI_FILE, DEFERRED_FILE]:
            if os.path.exists(f):
                with open(f, 'r', encoding='utf-8') as file:
                    all_to_check.extend([l.strip() for l in file if 'vless://' in l])
        
        for link in set(all_to_check):
            is_ok, status_code = deep_kill_check(link)
            if not is_ok:
                base = link.split("#")[0].strip()
                
                # 1. УДАЛЯЕМ ВЕЗДЕ (из wifi.txt, deferred.txt, 1.txt)
                remove_from_all(base)
                
                # 2. В БАН ТОЛЬКО ЕСЛИ НЕДОСТУПЕН (Н/Д)
                if status_code == 404:
                    print(f"💀 КИЛЛЕР (БАН): {base[:30]} - СДОХ (Н/Д)")
                    add_to_blacklist(base)
                
                # 3. ЕСЛИ ТОРМОЗ (>1000мс) - ПРОСТО УДАЛИЛИ И ВСЁ
                elif status_code == 1001:
                    print(f"🐢 ТОРМОЗ: {base[:30]} - Удален из списков (>1000мс), НЕ забанен")
                
                else:
                    print(f"⚠️ ВЫБРОС: {base[:30]} - Нестабилен, удален из списков")
        
        time.sleep(60) # Пауза между кругами ада # Пауза между кругами ада

if __name__ == "__main__":
    main_monitor()
