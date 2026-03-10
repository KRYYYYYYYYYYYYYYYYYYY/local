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
    with open(PINNED_FILE, 'r') as f:
        return base_part in f.read()

def add_to_blacklist(base_part):
    existing = set()
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            existing = {line.strip() for line in f}
    if base_part not in existing:
        with open(BLACKLIST_FILE, 'a') as f:
            f.write(base_part + "\n")

def remove_from_all(base_part):
    for path in [WIFI_FILE, DEFERRED_FILE, INPUT_FILE]:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = [l for l in lines if base_part not in l]
            if len(lines) != len(new_lines):
                with open(path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

def deep_kill_check(link):
    base_part = link.split("#")[0].strip()
    if is_pinned(base_part): return True, 0 # ИММУНИТЕТ
    
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
                # 3. ВЫКИДЫВАЕМ ИЗ СПИСКОВ В ЛЮБОМ СЛУЧАЕ
                remove_from_all(base)
                
                # 4. В БАН ТОЛЬКО ЕСЛИ СДОХ ИЛИ > 1000мс
                if status_code == 404 or status_code == 1001:
                    print(f"💀 КИЛЛЕР (БАН): {base[:30]} - Сдох или >1000мс")
                    add_to_blacklist(base)
                else:
                    # Если какая-то другая ошибка (джиттер и т.д.) - просто выкидываем
                    print(f"⚠️ ВЫБРОС (VETTED): {base[:30]} - Не прошел проверку, но жив")
        
        time.sleep(60) # Пауза между кругами ада

if __name__ == "__main__":
    main_monitor()
