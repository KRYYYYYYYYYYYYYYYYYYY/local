import socket, time, os, ssl, re, json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Настройки путей
PINNED_FILE = 'test1/pinned.txt'
RANK_FILE = 'test1/ranking.json'
VETTED_FILE = 'test1/vetted.txt'
THRESHOLD = 50 

# Блокировка для безопасной записи в файлы из разных потоков
file_lock = threading.Lock()

HOST_PORT_RE = re.compile(r'@(?P<host>[A-Za-z0-9.-]+):(?P<port>\d+)')

def extract_host_port(link: str) -> tuple[str | None, int | None]:
    m = HOST_PORT_RE.search(link)
    if not m: return None, None
    host, port_str = m.group("host"), m.group("port")
    if ":" in host or "[" in host or "]" in host: return None, None
    try:
        port = int(port_str)
        return (host, port) if 1 <= port <= 65535 else (None, None)
    except: return None, None

def build_tls_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def torture_check(link):
    host, port = extract_host_port(link)
    if not host or not port: return False
    is_tls = "security=tls" in link.lower() or "security=reality" in link.lower()
    sni = re.search(r"sni=([^&?#]+)", link)
    server_hostname = sni.group(1) if sni else host

    total_attempts = 20 
    for i in range(total_attempts):
        try:
            with socket.create_connection((host, port), timeout=7) as s:
                if is_tls:
                    ctx = build_tls_context()
                    with ctx.wrap_socket(s, server_hostname=server_hostname):
                        pass
                else:
                    s.sendall(b'\x05\x01\x00')
                    s.settimeout(2)
                    s.recv(2)
            if i < total_attempts - 1:
                time.sleep(60) 
        except:
            return False
    return True

def process_pin_commands(token, repo, vetted_list):
    if not token or not repo: return vetted_list
    try:
        cmd = ['gh', 'issue', 'list', '--repo', repo, '--label', 'pin_control', '--json', 'body', '--limit', '1']
        pin_read = subprocess.check_output(cmd, env={**os.environ, "GH_TOKEN": token}).decode()
        if pin_read and pin_read != "[]":
            issue_data = json.loads(pin_read)[0]
            to_pin = re.findall(r'- \[x\] (vless://[^\s#\s]+)', issue_data['body'])
            if to_pin:
                added_bases = set()
                current_p = []
                if os.path.exists(PINNED_FILE):
                    with open(PINNED_FILE, 'r', encoding='utf-8') as f:
                        current_p = [l.strip().split('#')[0] for l in f]
                with open(PINNED_FILE, 'a', encoding='utf-8') as pf:
                    for link in to_pin:
                        base = link.strip()
                        if base not in current_p:
                            pf.write(base + "\n")
                            added_bases.add(base)
                if added_bases:
                    new_vetted = [v for v in vetted_list if v.split('#')[0].strip() not in added_bases]
                    with open(VETTED_FILE, 'w', encoding='utf-8') as vf:
                        vf.write("\n".join(new_vetted) + ("\n" if new_vetted else ""))
                    return new_vetted
    except: pass
    return vetted_list

def main_torturer():
    token = os.getenv("GH_TOKEN")
    repo = os.getenv("GH_REPO")

    if not os.path.exists(RANK_FILE): return
    try:
        with open(RANK_FILE, 'r', encoding='utf-8') as f:
            ranking_db = json.load(f)
    except: ranking_db = {}

    if os.path.exists(VETTED_FILE):
        with open(VETTED_FILE, 'r', encoding='utf-8') as f:
            vetted_list = [l.strip() for l in f if 'vless://' in l]
    else: vetted_list = []

    vetted_list = process_pin_commands(token, repo, vetted_list)
    vetted_set = {v.split('#')[0].strip() for v in vetted_list}
    
    pinned_set = set()
    if os.path.exists(PINNED_FILE):
        with open(PINNED_FILE, 'r', encoding='utf-8') as f:
            pinned_set = {l.split('#')[0].strip() for l in f if 'vless://' in l}

    candidates = []
    for base, data in ranking_db.items():
        rank = data.get("rank", 0) if isinstance(data, dict) else data
        link = data.get("link", base) if isinstance(data, dict) else base
        
        # Берем либо сильных (на повышение), либо совсем слабых (на удаление)
        if (rank >= THRESHOLD or rank <= 0) and base not in vetted_set and base not in pinned_set:
            candidates.append((base, link))

    if not candidates: return

    # --- МНОГОПОТОЧНОСТЬ ---
    MAX_THREADS = 15
    dead_to_remove = [] # Список для автоудаления

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_server = {executor.submit(torture_check, link): (base, link) for base, link in candidates}

        for future in as_completed(future_to_server):
            base, full_link = future_to_server[future]
            try:
                success = future.result()
                if success:
                    with file_lock:
                        with open(VETTED_FILE, 'a', encoding='utf-8') as f:
                            f.write(full_link + "\n")
                    if isinstance(ranking_db.get(base), dict):
                        ranking_db[base]['rank'] = 0 
                else:
                    if isinstance(ranking_db.get(base), dict):
                        old_rank = ranking_db[base].get('rank', 0)
                        
                        # Если он УЖЕ был 0 и снова провалился — в список на удаление
                        if old_rank <= 0:
                            dead_to_remove.append(base)
                            print(f"🧹 {base[:20]} окончательно удален (стабильный 0).")
                        else:
                            # Иначе просто штрафуем
                            ranking_db[base]['rank'] = max(0, old_rank - 30)
            except: pass

    # Удаляем "мертвецов" из базы
    for dead_base in dead_to_remove:
        if dead_base in ranking_db:
            del ranking_db[dead_base]

    with open(RANK_FILE, 'w', encoding='utf-8') as f:
        json.dump(ranking_db, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main_torturer()
