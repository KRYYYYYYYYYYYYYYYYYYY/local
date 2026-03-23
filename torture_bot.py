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
BLACKLIST_FILE = 'test1/blacklist.txt'
WIFI_FILE = 'kr/mob/wifi.txt'
DEFERRED_FILE = 'test1/deferred.txt'
INPUT_FILE = 'test1/1.txt'
FAVORITES_FILE = 'test1/favorites.txt'
THRESHOLD = 50
PROBE_TIMEOUT = 3
TOTAL_ATTEMPTS = 20
SLEEP_BETWEEN_ATTEMPTS = 60

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

def probe_vless_l7(link: str, target_sni: str, timeout_sec: int = PROBE_TIMEOUT) -> int:
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
    for i in range(TOTAL_ATTEMPTS):
        ok = False

        tried_sni: set[str] = set()
        for cand_sni in extract_sni_candidates(link):
            cand_sni = cand_sni.strip()
            if not cand_sni or cand_sni in tried_sni:
                continue
            tried_sni.add(cand_sni)
            if probe_vless_l7(link, cand_sni, timeout_sec=PROBE_TIMEOUT) > 0:
                ok = True
                break

        if not ok:
            fallback_sni = (extract_sni(link) or host).strip()
            if fallback_sni and fallback_sni not in tried_sni:
                ok = probe_vless_l7(link, fallback_sni, timeout_sec=PROBE_TIMEOUT) > 0

        if not ok:
            return False

        if i < TOTAL_ATTEMPTS - 1:
            time.sleep(SLEEP_BETWEEN_ATTEMPTS)

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

def load_vless_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [l.strip() for l in f if 'vless://' in l]


def add_to_blacklist(base_part: str) -> None:
    existing = set(load_vless_lines(BLACKLIST_FILE))
    if base_part not in existing:
        with open(BLACKLIST_FILE, 'a', encoding='utf-8') as f:
            f.write(base_part + "\n")


def remove_from_all(base_part: str) -> None:
    for path in [WIFI_FILE, DEFERRED_FILE, INPUT_FILE, VETTED_FILE]:
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        filtered = [l for l in lines if l.split('#')[0].strip() != base_part]
        if len(filtered) != len(lines):
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(filtered)


def update_issue(repo: str, label: str, body: str, env: dict) -> None:
    try:
        out = subprocess.check_output(
            ['gh', 'issue', 'list', '--repo', repo, '--label', label, '--json', 'number', '--limit', '1'],
            env=env,
        ).decode('utf-8')
        data = json.loads(out)
        if not data:
            return
        num = str(data[0]['number'])
        tmp_file = f"tmp_body_{label}.txt"
        with open(tmp_file, 'w', encoding='utf-8') as f:
            f.write(body)
        subprocess.run(['gh', 'issue', 'edit', num, '--repo', repo, '--body-file', tmp_file], env=env, check=True)
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
    except Exception as e:
        print(f"⚠️ Ошибка обновления панели {label}: {e}")


def get_wifi_candidates(pinned_list: list[str], fav_list: list[str] | None = None) -> list[str]:
    fav_list = fav_list or []
    if not os.path.exists(WIFI_FILE):
        return []
    excluded = {p.split('#')[0].strip() for p in pinned_list}
    excluded.update({f.split('#')[0].strip() for f in fav_list})
    out: list[str] = []
    with open(WIFI_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if 'vless://' not in line:
                continue
            if line.split('#')[0].strip() not in excluded:
                out.append(line)
    return out


def refresh_all_panels(token: str, repo: str, ranking_db: dict, vetted_list: list[str], pinned_list: list[str]) -> None:
    if not token or not repo:
        return
    env_gh = {**os.environ, "GH_TOKEN": token}
    ts = time.strftime("%d.%m.%Y %H:%M:%S")

    body_ctrl = f"### 🎮 Панель Blacklist\n🕒 `{ts}`\n\n- [ ] 💀 **ПОДТВЕРДИТЬ_БАН**\n\n---\n\n"
    for link in get_wifi_candidates(pinned_list, load_vless_lines(FAVORITES_FILE)):
        body_ctrl += f"- [ ] {link}\n"
    update_issue(repo, 'control', body_ctrl, env_gh)

    body_pin = f"### 💎 Кандидаты в Элиту\n🕒 `{ts}`\n\n- [ ] ✅ **ПРИМЕНИТЬ_PIN_BAN**\n\n---\n\n"
    for link in vetted_list:
        body_pin += f"- [ ] PIN: {link}\n- [ ] BAN: {link}\n\n"
    update_issue(repo, 'pin_control', body_pin, env_gh)

    body_unpin = f"### 👑 Управление Закрепами\n🕒 `{ts}`\n\n- [ ] 🔓 **ПОДТВЕРДИТЬ_РАСПИН**\n\n---\n\n"
    for link in pinned_list:
        body_unpin += f"- [ ] {link}\n"
    update_issue(repo, 'unpin_control', body_unpin, env_gh)


def process_all_controls(token: str, repo: str, vetted_list: list[str], pinned_list: list[str], ranking_db: dict) -> tuple[list[str], list[str], bool]:
    if not token or not repo:
        return vetted_list, pinned_list, False
    env_gh = {**os.environ, "GH_TOKEN": token}
    executed_any = False

    def checked_links(text: str) -> list[str]:
        return [x.strip().rstrip(':') for x in re.findall(r'\[[xX]\]\s+(vless://[^\n\r`\'"]+)', text)]

    try:
        # control: BAN
        out = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'control', '--json', 'body', '--limit', '1'], env=env_gh).decode('utf-8')
        data = json.loads(out)
        if data and "ПОДТВЕРДИТЬ_БАН" in data[0]['body']:
            for full in checked_links(data[0]['body']):
                base = full.split('#')[0].strip()
                add_to_blacklist(base)
                remove_from_all(base)
                ranking_db.pop(base, None)
                vetted_list = [v for v in vetted_list if v.split('#')[0].strip() != base]
                executed_any = True

        # pin_control: PIN/BAN
        out = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'pin_control', '--json', 'body', '--limit', '1'], env=env_gh).decode('utf-8')
        data = json.loads(out)
        if data and "ПРИМЕНИТЬ_PIN_BAN" in data[0]['body']:
            body = data[0]['body']
            to_pin = [x.strip().rstrip(':') for x in re.findall(r'\[[xX]\]\s+PIN:\s+(vless://[^\n\r`\'"]+)', body)]
            to_ban = [x.strip().rstrip(':') for x in re.findall(r'\[[xX]\]\s+BAN:\s+(vless://[^\n\r`\'"]+)', body)]
            pinned_bases = {p.split('#')[0].strip() for p in pinned_list}
            for full in to_pin:
                base = full.split('#')[0].strip()
                if base not in pinned_bases:
                    pinned_list.append(full)
                    pinned_bases.add(base)
                vetted_list = [v for v in vetted_list if v.split('#')[0].strip() != base]
                executed_any = True
            for full in to_ban:
                base = full.split('#')[0].strip()
                add_to_blacklist(base)
                remove_from_all(base)
                ranking_db.pop(base, None)
                vetted_list = [v for v in vetted_list if v.split('#')[0].strip() != base]
                executed_any = True

        # unpin_control
        out = subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--label', 'unpin_control', '--json', 'body', '--limit', '1'], env=env_gh).decode('utf-8')
        data = json.loads(out)
        if data and "ПОДТВЕРДИТЬ_РАСПИН" in data[0]['body']:
            to_unpin = {x.split('#')[0].strip() for x in checked_links(data[0]['body'])}
            if to_unpin:
                pinned_list = [p for p in pinned_list if p.split('#')[0].strip() not in to_unpin]
                executed_any = True

    except Exception as e:
        print(f"⚠️ Ошибка обработки issue-команд: {e}")

    return vetted_list, pinned_list, executed_any

def kill_sibling_torturer(current_pid: int) -> bool:
    """Убивает другой запущенный экземпляр torture_bot.py. Возвращает True если был убит."""
    killed = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if proc.info['pid'] == current_pid:
            continue
        cmdline = proc.info.get('cmdline')
        if cmdline and 'torture_bot.py' in ' '.join(cmdline):
            try:
                p = psutil.Process(proc.info['pid'])
                p.terminate()
                p.wait(timeout=10)
                print(f"🛑 Остановлен старый процесс (PID {proc.info['pid']}).")
                killed = True
            except Exception as e:
                print(f"⚠️ Не удалось завершить процесс {proc.info['pid']}: {e}")
    return killed


def main_torturer():
    if go_lib is None:
        print("❌ Go checker не инициализирован. Выход.")
        return

    current_pid = os.getpid()
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    token = os.getenv("GH_TOKEN")
    repo = os.getenv("GH_REPO") or os.getenv("GITHUB_REPOSITORY")

    # При issues-событии: убиваем старый процесс и продолжаем с приоритетом issues.
    # При остальных событиях: если уже есть запущенный экземпляр — выходим.
    if event_name == "issues":
        kill_sibling_torturer(current_pid)
    else:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if proc.info['pid'] != current_pid:
                cmdline = proc.info.get('cmdline')
                if cmdline and 'torture_bot.py' in ' '.join(cmdline):
                    print(f"🛑 Обнаружен запущенный близнец (PID {proc.info['pid']}). Самоликвидация.")
                    return

    if not os.path.exists(RANK_FILE):
        print(f"📭 Файл {RANK_FILE} не найден. Некого пытать.")
        return

    try:
        with open(RANK_FILE, 'r', encoding='utf-8') as f:
            raw_ranking_db = json.load(f)
            ranking_db = {}
            if isinstance(raw_ranking_db, dict):
                for base, data in raw_ranking_db.items():
                    if isinstance(data, dict):
                        ranking_db[base] = data
                    elif isinstance(data, int):
                        ranking_db[base] = {"rank": int(data), "link": base}
    except Exception:
        ranking_db = {}
        print("❌ Ошибка чтения JSON.")

    vetted_list = load_vless_lines(VETTED_FILE)
    pinned_list = load_vless_lines(PINNED_FILE)

    vetted_list = process_pin_commands(token, repo, vetted_list)

    vetted_list, pinned_list, executed = process_all_controls(token, repo, vetted_list, pinned_list, ranking_db)
    if executed:
        with open(VETTED_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(vetted_list) + ("\n" if vetted_list else ""))
        with open(PINNED_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(pinned_list) + ("\n" if pinned_list else ""))
        with open(RANK_FILE, 'w', encoding='utf-8') as f:
            json.dump(ranking_db, f, ensure_ascii=False, indent=4)
        refresh_all_panels(token, repo, ranking_db, vetted_list, pinned_list)
        print("✅ Issue-команды применены.")
        # После обработки issues — продолжаем к кандидатам (не выходим).
    else:
        # Нет issue-команд: обновляем панели (актуализируем timestamp и состояние).
        refresh_all_panels(token, repo, ranking_db, vetted_list, pinned_list)

    if event_name not in {"schedule", "workflow_dispatch", "issues"}:
        print("☕ Нет подтвержденных issue-команд и это не расписание/manual/issues. Выход.")
        return

    vetted_set = {v.split('#')[0].strip() for v in vetted_list}

    pinned_set = {p.split('#')[0].strip() for p in pinned_list}

    print(f"📊 Всего в базе: {len(ranking_db)} | В исключениях (Vetted/Pinned): {len(vetted_set | pinned_set)}")

    candidates = []
    seen_endpoints: set[tuple[str, int]] = set()

    for base, data in ranking_db.items():
        rank = data.get("rank", 0) if isinstance(data, dict) else data
        link = data.get("link", base) if isinstance(data, dict) else base

        # Берем либо сильных (на повышение), либо совсем слабых (на удаление)
        if (rank >= THRESHOLD or rank <= 0) and base not in vetted_set and base not in pinned_set:
            host, port = extract_host_port(link)
            endpoint_key = (host, port) if host and port else None
            if endpoint_key and endpoint_key in seen_endpoints:
                print(f"↪️ [INSPECTOR] skip duplicate endpoint {host}:{port}")
                continue
            if endpoint_key:
                seen_endpoints.add(endpoint_key)
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
                        ranking_db[base] = {"rank": 0, "link": full_link}
                else:
                    old_rank = 0
                    if isinstance(ranking_db.get(base), dict):
                        old_rank = int(ranking_db[base].get('rank', 0))

                    # Если он УЖЕ был 0 и снова провалился — в список на удаление
                    if old_rank <= 0:
                        dead_to_remove.append(base)
                        print(f"🧹 {base[:20]}... удален (стабильный 0).")
                    else:
                        # Иначе просто штрафуем
                        ranking_db[base] = {"rank": max(0, old_rank - 30), "link": full_link}
                        print(f"❌ {base[:20]}... провал (штраф -30).")
            except Exception:
                pass

    # Удаляем "мертвецов" из базы
    for dead_base in dead_to_remove:
        if dead_base in ranking_db:
            del ranking_db[dead_base]

    with open(RANK_FILE, 'w', encoding='utf-8') as f:
        json.dump(ranking_db, f, ensure_ascii=False, indent=4)

    ranked = []
    for base, data in ranking_db.items():
        if isinstance(data, dict):
            ranked.append((base, int(data.get("rank", 0))))
    ranked.sort(key=lambda x: x[1], reverse=True)
    if ranked:
        print("🏆 [INSPECTOR] TOP-10:")
        for i, (base, score) in enumerate(ranked[:10], start=1):
            print(f"   {i}) {score} — {base[:72]}")
    refresh_all_panels(token, repo, ranking_db, load_vless_lines(VETTED_FILE), pinned_list)
    print("💾 Все изменения сохранены.")
    
if __name__ == "__main__":
    init_checker_lib()
    main_torturer()
