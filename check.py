import ctypes
import ipaddress
import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request
import uuid as uuidlib
from concurrent.futures import ThreadPoolExecutor, as_completed


# --- Пути ---
INPUT_FILE = "test1/1.txt"
OUTPUT_FILE = "kr/mob/wifi.txt"
STATUS_FILE = "test1/status.json"
BLACKLIST_FILE = "test1/blacklist.txt"
DEFERRED_FILE = "test1/deferred.txt"
PINNED_FILE = "test1/pinned.txt"
RANKING_FILE = "test1/ranking.json"

EXTERNAL_SOURCE_URL = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_SS%2BAll_RUS.txt",
    "https://raw.githubusercontent.com/KiryaScript/white-lists/refs/heads/main/githubmirror/26.txt",
    "https://raw.githubusercontent.com/KiryaScript/white-lists/refs/heads/main/githubmirror/27.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt",
]

HEADER = """# profile-title: 🏴WIFI🏴
# remark: 🏴WIFI🏴
# announce: Подписка для использования на wifi. P.s. Подписка бесплатная, поэтому не гарантирует хороших серверов, в общем, а тем более 24/7. 
# profile-update-interval: 2
"""

ALLOWED_COUNTRIES = {"US", "DE", "NL", "GB", "FR", "FI", "SG", "JP", "PL", "TR", "RU"}
GRACE_PERIOD = 2 * 24 * 60 * 60
MAX_TO_CHECK = 300
MAX_TOTAL_CHECK = 1800
MAX_SUB_LINKS = 200
MAX_PINNED_IN_SUB = 50
PROBE_TIMEOUT = 3
CHECK_WORKERS = 6
STRICT_L7 = os.getenv("CHECK_STRICT_L7", "0").strip().lower() in {"1", "true", "yes"}
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-A336B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 16; SM-A336B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.119 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A336B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.179 Mobile Safari/537.36 happ/3.15.1",
    "Happ/3.15.1",
    "okhttp/4.12.0 v2rayNG/1.12.28",
]

go_lib = None


def init_checker_lib() -> None:
    global go_lib
    lib_path = os.path.abspath("libchecker.so")
    if not os.path.exists(lib_path):
        print("❌ libchecker.so не найден, L7-проверка отключена")
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

def probe_vless_l7(link: str, target_sni: str, timeout: int = 5) -> int:
    if go_lib is None:
        return 0
    try:
        parsed = urllib.parse.urlparse(link)
        params = urllib.parse.parse_qs(parsed.query)       
        _, host, port = extract_host_port(link)
        if not host or not port:
            return 0
            
        raw_uuid = urllib.parse.unquote(parsed.username or "").strip()
        try:
            uuid = str(uuidlib.UUID(raw_uuid))
        except Exception:
            return 0
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
                int(timeout),
            )
        )

    except Exception as exc:
        print(f"⚠️ L7 checker error: {exc}")
        return 0


def has_valid_uuid(link: str) -> bool:
    parsed = urllib.parse.urlparse(link)
    raw_uuid = urllib.parse.unquote(parsed.username or "").strip()
    if not raw_uuid:
        return False
    try:
        uuidlib.UUID(raw_uuid)
        return True
    except Exception:
        return False

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def rank_score(base: str, ranking_db: dict) -> int:
    data = ranking_db.get(base, 0)
    if isinstance(data, dict):
        return int(data.get("rank", 0))
    if isinstance(data, int):
        return int(data)
    return 0

def pick_user_agent() -> str:
    return DEFAULT_USER_AGENTS[int(time.time_ns()) % len(DEFAULT_USER_AGENTS)]


def load_lines(path: str, contains: str | None = None) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if contains:
        return [line for line in lines if contains in line]
    return lines


def save_lines(path: str, lines: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


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

    if parsed.hostname:
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            if parsed.hostname not in candidates:
                candidates.append(parsed.hostname)
    return candidates


def is_ipv6(host: str) -> bool:
    if not host:
        return False
    try:
        return isinstance(ipaddress.ip_address(host.strip("[]")), ipaddress.IPv6Address)
    except ValueError:
        return False

def extract_host_port(link: str):
    match = re.search(r"@(?:\[([0-9a-fA-F:]+)\]|([\w.-]+)):(\d+)", link)
    if not match:
        return None, None, None
    host = match.group(1) or match.group(2)
    return match.group(0), host, match.group(3)


def rebuild_link_name(link: str, new_name: str) -> str:
    base, _, fragment = link.partition("#")
    if not fragment:
        return f"{base}#{urllib.parse.quote(new_name)}"

    frag_decoded = urllib.parse.unquote(fragment)
    if "PINNED" in frag_decoded.upper():
        return link

    match = re.match(r"^([^\w\s\d]|[^\x00-\x7F])+", frag_decoded)
    if match:
        prefix = match.group(0).strip()
        return f"{base}#{urllib.parse.quote(prefix + ' ' + new_name)}"

    return f"{base}#{urllib.parse.quote(new_name)}"

def get_country_code(host: str, cache: dict[str, str]) -> str:
    ip = host
    if not is_ipv6(host):
        try:
            ip = socket.gethostbyname(host) if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else host
        except Exception:
            ip = host

    if ip in cache:
        return cache[ip]

    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        req = urllib.request.Request(url, headers={"User-Agent": pick_user_agent()})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                code = data.get("countryCode", "Unknown")
                cache[ip] = code
                return code
    except Exception:
        pass
    return "Unknown"

def fetch_external_servers() -> list[str]:
    all_configs: list[str] = []
    for url in EXTERNAL_SOURCE_URL:
        success = False
        for attempt in range(3):
            try:
                print(f"🌐 source {url} (attempt {attempt + 1}/3)", flush=True)
                req = urllib.request.Request(url.strip(), headers={"User-Agent": pick_user_agent()})
                with urllib.request.urlopen(req, timeout=15) as response:
                    content = response.read().decode("utf-8")
                    found = [line.strip() for line in content.splitlines() if "vless://" in line]
                    all_configs.extend(found)
                    print(f"📥 {url}: +{len(found)}")
                    success = True
                    break
            except Exception as exc:
                wait_time = (attempt + 1) * 3
                err_text = str(exc)
                if "Temporary failure in name resolution" in err_text:
                    print(f"⚠️ DNS glitch for {url}: {exc}; retry {wait_time}s", flush=True)
                else:
                    print(f"❌ download fail {url}: {exc}; retry {wait_time}s", flush=True)
                time.sleep(wait_time)
        if not success:
            print(f"⚠️ source skipped: {url}")

    return all_configs


def dedupe_links(links: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for link in links:
        if "vless://" not in link:
            continue
        base = link.split("#", 1)[0].strip()
        if base in seen:
            continue
        seen.add(base)
        unique.append(link)
    return unique

def probe_link_latency(link: str) -> int:
    latency = 0
    tried_sni: set[str] = set()
    for cand_sni in extract_sni_candidates(link):
        cand_sni = cand_sni.strip()
        if not cand_sni or cand_sni in tried_sni:
            continue
        tried_sni.add(cand_sni)
        latency = probe_vless_l7(link, cand_sni, timeout=PROBE_TIMEOUT)
        if latency > 0:
            return latency

    fallback_sni = extract_sni(link).strip()
    if fallback_sni and fallback_sni not in tried_sni:
        return probe_vless_l7(link, fallback_sni, timeout=PROBE_TIMEOUT)
    return 0

def probe_tcp_latency(host: str, port: str, timeout_sec: float = 1.8) -> int:
    try:
        start = time.time()
        with socket.create_connection((host, int(port)), timeout=timeout_sec):
            return int((time.time() - start) * 1000)
    except Exception:
        return 0


def main() -> None:
    countries_cache = load_json("test1/countries_cache.json", {})
    history = load_json(STATUS_FILE, {})
    raw_ranking_db = load_json(RANKING_FILE, {})
    ranking_db: dict[str, dict] = {}
    for base, data in raw_ranking_db.items() if isinstance(raw_ranking_db, dict) else []:
        if isinstance(data, dict):
            ranking_db[base] = data
        elif isinstance(data, int):
            ranking_db[base] = {"rank": int(data), "link": base}
    blacklist = set(load_lines(BLACKLIST_FILE))
    pinned_list = load_lines(PINNED_FILE, contains="vless://")
    deferred = load_lines(DEFERRED_FILE)
    current_base = load_lines(INPUT_FILE)
    had_deferred_at_start = len(deferred) > 0
    external_loaded = False

    if had_deferred_at_start:
        queue = dedupe_links(pinned_list + deferred + current_base)
        print(f"📦 pinned={len(pinned_list)} deferred={len(deferred)} queue={len(queue)} (external postponed)")
    else:
        external = fetch_external_servers()
        external_loaded = True
        queue = dedupe_links(pinned_list + external + current_base)
        print(f"📦 pinned={len(pinned_list)} deferred=0 external={len(external)} queue={len(queue)}")

    pinned_bases = {p.split("#", 1)[0].strip() for p in pinned_list}
    queue_non_pinned = [q for q in queue if q.split("#", 1)[0].strip() not in pinned_bases]
    queue_non_pinned.sort(key=lambda q: rank_score(q.split("#", 1)[0].strip(), ranking_db), reverse=True)
    queue = pinned_list + queue_non_pinned

    working_for_sub: list[str] = []
    working_for_base: list[str] = []
    deferred_next: list[str] = []
    new_history: dict[str, float] = {}

    # 1) фиксированные в начало (до лимита закрепов)
    counter = 1
    for p in pinned_list:
        if len(working_for_sub) >= MAX_PINNED_IN_SUB:
            deferred_next.append(p)
            continue
        base = p.split("#", 1)[0].strip()
        raw_name = urllib.parse.unquote(p.split("#", 1)[1]) if "#" in p else ""
        flag_match = re.match(r"^([^\w\s\d]+)", raw_name)
        flag = flag_match.group(1).strip() if flag_match else ""
        fixed_name = f"{flag} 💎 [PINNED] {counter}".strip()
        working_for_sub.append(f"{base}#{urllib.parse.quote(fixed_name)}")
        counter += 1

    # 2) обычная проверка
    checked = 0
    now = time.time()
    idx = 0
    workers = max(1, int(os.getenv("CHECK_WORKERS", str(CHECK_WORKERS))))
    print(f"⚙️ probing mode: workers={workers} strict_l7={STRICT_L7}", flush=True)
    while len(working_for_sub) < MAX_SUB_LINKS and checked < MAX_TOTAL_CHECK:
        remaining_slots = MAX_SUB_LINKS - len(working_for_sub)
        batch_target = min(MAX_TO_CHECK, max(8, remaining_slots * 2))
        candidates_to_probe: list[tuple[str, str, str, str]] = []
        while len(candidates_to_probe) < batch_target and checked < MAX_TOTAL_CHECK:
            if idx >= len(queue):
                if had_deferred_at_start and not external_loaded:
                    print("🧩 deferred exhausted -> loading external sources now", flush=True)
                    external = fetch_external_servers()
                    queue = dedupe_links(queue + external)
                    external_loaded = True
                    print(f"📦 external loaded={len(external)} new_queue={len(queue)}", flush=True)
                    continue
                break

            link = queue[idx]
            idx += 1
            base = link.split("#", 1)[0].strip()
            if base in pinned_bases or base in blacklist:
                continue
            if not has_valid_uuid(base):
                continue
            endpoint, host, port = extract_host_port(base)
            if not endpoint or not host or not port:
                continue
            checked += 1
            print(f"🔍 queued {checked}/{MAX_TOTAL_CHECK} {host}:{port}", flush=True)
            candidates_to_probe.append((base, link, host, port))

        if not candidates_to_probe:
            break

        print(f"⚙️ start probing batch: candidates={len(candidates_to_probe)} workers={workers}", flush=True)
        executor = ThreadPoolExecutor(max_workers=workers)
        stop_batch_early = False
        try:
            future_map = {
                executor.submit(probe_link_latency, link): (base, link, host, port)
                for base, link, host, port in candidates_to_probe
            }

            for future in as_completed(future_map):
                if len(working_for_sub) >= MAX_SUB_LINKS:
                    stop_batch_early = True
                    break
                base, link, host, port = future_map[future]

                latency = 0

                try:
                    latency = int(future.result() or 0)
                except Exception:
                    latency = 0

                if latency <= 0 and not STRICT_L7:
                    tcp_latency = probe_tcp_latency(host, port, timeout_sec=1.8)
                    if tcp_latency > 0:
                        latency = tcp_latency + 800
                        print(f"🟡 tcp-fallback alive {host}:{port} ({tcp_latency}ms)", flush=True)

                if latency <= 0:
                    print(f"💀 dead/no-l7 {host}:{port}", flush=True)
                    fail_time = float(history.get(base, now))
                    if now - fail_time > 86400:
                        blacklist.add(base)
                    elif now - fail_time <= GRACE_PERIOD:
                        new_history[base] = fail_time
                    if base in ranking_db:
                        ranking_db.pop(base, None)
                    continue

                country = get_country_code(host, countries_cache)
                if country not in ALLOWED_COUNTRIES:
                    print(f"🌍 skip {host}:{port} country={country}", flush=True)
                    continue

                if len(working_for_sub) >= MAX_SUB_LINKS:
                    continue

                sub_link = base
                if "sni=" not in sub_link.lower() and not is_ipv6(host):
                    sub_link += ("&" if "?" in sub_link else "?") + f"sni={host}"

                final = rebuild_link_name(sub_link, f"wifi {counter} [{latency}ms]")
                working_for_sub.append(final)
                working_for_base.append(base)
                print(f"✅ {len(working_for_sub)}/{MAX_SUB_LINKS}: {host}:{port} {country} {latency}ms")
                old_rank = 0
                if isinstance(ranking_db.get(base), dict):
                    old_rank = int(ranking_db[base].get("rank", 0))
                elif isinstance(ranking_db.get(base), int):
                    old_rank = int(ranking_db.get(base, 0))
                new_rank = old_rank + 1
                ranking_db[base] = {
                    "rank": new_rank,
                    "link": final,
                    "country": country,
                    "latency": int(latency),
                    "last_seen": int(now),
                }
                print(f"🏅 rank {new_rank}: {host}:{port}", flush=True)
                counter += 1
        finally:
            executor.shutdown(wait=not stop_batch_early, cancel_futures=stop_batch_early)

    if idx < len(queue):
        deferred_next.extend(queue[idx:])

    # финальные лимиты и дедуп
    working_for_sub = dedupe_links(working_for_sub)[:MAX_SUB_LINKS]
    deferred_next = dedupe_links(deferred_next)

    # save
    save_lines(DEFERRED_FILE, deferred_next)
    save_lines(INPUT_FILE, dedupe_links(pinned_list + working_for_base))
    save_lines(BLACKLIST_FILE, sorted(blacklist))

    with open("test1/countries_cache.json", "w", encoding="utf-8") as f:
        json.dump(countries_cache, f, ensure_ascii=False, indent=2)

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

    with open(RANKING_FILE, "w", encoding="utf-8") as f:
        json.dump(ranking_db, f, ensure_ascii=False, indent=2)

    top_ranked: list[tuple[str, int]] = []
    for base, data in ranking_db.items():
        if isinstance(data, dict):
            top_ranked.append((base, int(data.get("rank", 0))))
    top_ranked.sort(key=lambda x: x[1], reverse=True)
    if top_ranked:
        print("📊 TOP ranks:")
        for i, (base, score) in enumerate(top_ranked[:10], start=1):
            print(f"  {i}. {score} — {base[:72]}")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER.strip() + "\n\n" + "\n".join(working_for_sub))

    print(f"🏁 done: sub={len(working_for_sub)} deferred={len(deferred_next)} checked={checked}")

if __name__ == "__main__":
    init_checker_lib()
    main()
