import ctypes
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil

# Настройки путей
PINNED_FILE = 'test1/pinned.txt'
RANK_FILE = 'test1/ranking.json'
VETTED_FILE = 'test1/vetted.txt'
THRESHOLD = 50

# Блокировка для безопасной записи в файлы из разных потоков
file_lock = threading.Lock()
go_lib = None

HOST_PORT_RE = re.compile(r'@(?:\[(?P<host6>[0-9a-fA-F:]+)\]|(?P<host>[A-Za-z0-9.-]+)):(?P<port>\d+)')


def init_checker_lib() -> None:
    global go_lib
    lib_path = os.path.abspath("libchecker.so")
    if not os.path.exists(lib_path):
        print("⚠️ libchecker.so не найден. Инспектор остановлен.")
        return

    go_lib = ctypes.cdll.LoadLibrary(lib_path)
    go_lib.CheckVlessL7.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    go_lib.CheckVlessL7.restype = ctypes.c_int


def extract_host_port(link: str) -> tuple[str | None, int | None]:
    m = HOST_PORT_RE.search(link)
    if not m:
        return None, None

    host = m.group("host6") or m.group("host")
    port_str = m.group("port")
    try:
        port = int(port_str)
        return (host, port) if 1 <= port <= 65535 else (None, None)
    except Exception:
        return None, None


def extract_sni(link: str) -> str:
    parsed = urllib.parse.urlparse(link)
    params = urllib.parse.parse_qs(parsed.query)
    return params.get("sni", [""])[0]


def extract_sni_candidates(link: str) -> list[str]:
    parsed = urllib.parse.urlparse(link)
    params = urllib.parse.parse_qs(parsed.query)
    candidates: list[str] = []

    for key in ("sni", "host"):
        val = params.get(key, [""])[0].strip()
        if val and val not in candidates:
            candidates.append(val)

    if parsed.hostname and parsed.hostname not in candidates:
        candidates.append(parsed.hostname)
    return candidates

def probe_vless_l7(link: str, target_sni: str, timeout_sec: int = 7) -> int:
    if go_lib is None:
        return 0

    host, port = extract_host_port(link)
    if not host or not port:
        return 0

    try:
        parsed = urllib.parse.urlparse(link)
        params = urllib.parse.parse_qs(parsed.query)
        uuid = parsed.username or ""
        pbk = params.get("pbk", [""])[0]
        sid = params.get("sid", [""])[0]
        flow = params.get("flow", [""])[0]

        return int(
            go_lib.CheckVlessL7(
                host.encode("utf-8"),
                int(port),
                uuid.encode("utf-8"),
                (target_sni or "").encode("utf-8"),
                pbk.encode("utf-8"),
                sid.encode("utf-8"),
                flow.encode("utf-8"),
                int(timeout_sec),
            )
        )
    except Exception:
        return 0

def torture_check(link: str) -> bool:
    host, port = extract_host_port(link)
    if not host or not port:
        return False

    total_attempts = 20
    for i in range(total_attempts):
        ok = False
        
        for cand_sni in extract_sni_candidates(link):
            if probe_vless_l7(link, cand_sni, timeout_sec=7) > 0:
                ok = True
                break

        if not ok:
            fallback_sni = extract_sni(link) or host
            ok = probe_vless_l7(link, fallback_sni, timeout_sec=7) > 0

        if not ok:
            return False

        if i < total_attempts - 1:
            time.sleep(60)

    return True


def process_pin_commands(token, repo, vetted_list):
    if not token or not repo:
        return vetted_list
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
    except Exception:
        pass
    return vetted_list

def main_torturer():
    if go_lib is None:
        print("❌ Go checker не инициализирован. Выход.")
        return

    # Проверка: не запущен ли уже другой такой же скрипт?
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if proc.info['pid'] != current_pid:
            cmdline = proc.info.get('cmdline')
            if cmdline and 'torture_bot.py' in ' '.join(cmdline):
                print(f"🛑 Обнаружен запущенный близнец (PID {proc.info['pid']}). Самоликвидация.")
                return

    token = os.getenv("GH_TOKEN")
    repo = os.getenv("GH_REPO")

    if not os.path.exists(RANK_FILE):
        print(f"📭 Файл {RANK_FILE} не найден. Некого пытать.")
        return

    try:
        with open(RANK_FILE, 'r', encoding='utf-8') as f:
            ranking_db = json.load(f)
    except Exception:
        ranking_db = {}
        print("❌ Ошибка чтения JSON.")

    
    if os.path.exists(VETTED_FILE):
        with open(VETTED_FILE, 'r', encoding='utf-8') as f:
            vetted_list = [l.strip() for l in f if 'vless://' in l]
    else:
        vetted_list = []
        
    vetted_list = process_pin_commands(token, repo, vetted_list)
    vetted_set = {v.split('#')[0].strip() for v in vetted_list}
    
    pinned_set = set()
    if os.path.exists(PINNED_FILE):
        with open(PINNED_FILE, 'r', encoding='utf-8') as f:
            pinned_set = {l.split('#')[0].strip() for l in f if 'vless://' in l}

    print(f"📊 Всего в базе: {len(ranking_db)} | В исключениях (Vetted/Pinned): {len(vetted_set | pinned_set)}")

    candidates = []

    for base, data in ranking_db.items():
        rank = data.get("rank", 0) if isinstance(data, dict) else data
        link = data.get("link", base) if isinstance(data, dict) else base

        # Берем либо сильных (на повышение), либо совсем слабых (на удаление)
        if (rank >= THRESHOLD or rank <= 0) and base not in vetted_set and base not in pinned_set:
            candidates.append((base, link))

    if not candidates:
        print(f"⌛ Кандидатов нет. (THRESHOLD: {THRESHOLD}). Ждем, пока кто-то наберет баллы.")
        return

    print(f"🔥 Начинаем пытки! Отобрано кандидатов: {len(candidates)}")

    # --- МНОГОПОТОЧНОСТЬ ---
    MAX_THREADS = 20
    dead_to_remove = []  # Список для автоудаления

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_server = {executor.submit(torture_check, link): (base, link) for base, link in candidates}

        for future in as_completed(future_to_server):
            base, full_link = future_to_server[future]
            try:
                success = future.result()
                if success:
                    print(f"🎖️ {base[:20]}... ПРОШЕЛ.")
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
                            print(f"🧹 {base[:20]}... удален (стабильный 0).")
                        else:
                            # Иначе просто штрафуем
                            ranking_db[base]['rank'] = max(0, old_rank - 30)
                            print(f"❌ {base[:20]}... провал (штраф -30).")
            except Exception:
                pass

    # Удаляем "мертвецов" из базы
    for dead_base in dead_to_remove:
        if dead_base in ranking_db:
            del ranking_db[dead_base]

    with open(RANK_FILE, 'w', encoding='utf-8') as f:
        json.dump(ranking_db, f, ensure_ascii=False, indent=4)
    print("💾 Все изменения сохранены.")
    
if __name__ == "__main__":
    init_checker_lib()
    main_torturer()
