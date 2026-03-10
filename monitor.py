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
    if is_pinned(base_part): return True # ИММУНИТЕТ
    
    host, port = extract_host_port(base_part)
    if not host: return False

    for _ in range(3): # 3 удара для точности
        try:
            start = time.time()
            with socket.create_connection((host, port), timeout=3.5) as s:
                # Если TLS/Reality - имитируем хендшейк
                if "security=tls" in link or "security=reality" in link:
                    ssl.create_default_context().wrap_socket(s, server_hostname=host)
                else:
                    s.sendall(b'\x16\x03\x01\x00\x00')
            lat = (time.time() - start) * 1000
            if lat > 1000: return False # Слишком медленно
            time.sleep(0.5)
        except: return False # Сдох
    return True

def main_monitor():
    start_run = time.time()
    while time.time() - start_run < 600: # 10 минут работы
        print(f"🕵️ Обход в {time.strftime('%H:%M:%S')}")
        
        all_to_check = []
        for f in [WIFI_FILE, DEFERRED_FILE]:
            if os.path.exists(f):
                with open(f, 'r', encoding='utf-8') as file:
                    all_to_check.extend([l.strip() for l in file if 'vless://' in l])
        
        for link in set(all_to_check):
            if not deep_kill_check(link):
                base = link.split("#")[0].strip()
                print(f"💀 КИЛЛЕР: Удаляю {base[:30]}")
                remove_from_all(base)
                add_to_blacklist(base)
        
        time.sleep(60) # Пауза между кругами ада

if __name__ == "__main__":
    main_monitor()
