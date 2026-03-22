import ctypes
import ipaddress
import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request


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
# announce: Подписка для использования на wifi.
# profile-update-interval: 2
"""

ALLOWED_COUNTRIES = {"US", "DE", "NL", "GB", "FR", "FI", "SG", "JP", "PL", "TR"}
GRACE_PERIOD = 2 * 24 * 60 * 60
MAX_TO_CHECK = 300
MAX_SUB_LINKS = 200
MAX_PINNED_IN_SUB = 80
PROBE_TIMEOUT = 3

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
                int(timeout),
            )
        )

    except Exception as exc:
        print(f"⚠️ L7 checker error: {exc}")
        return 0

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


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
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for url in EXTERNAL_SOURCE_URL:
        success = False
        for attempt in range(3):
            try:
                req = urllib.request.Request(url.strip(), headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response:
                    content = response.read().decode("utf-8")
                    found = [line.strip() for line in content.splitlines() if "vless://" in line]
                    all_configs.extend(found)
                    print(f"📥 {url}: +{len(found)}")
                    success = True
                    break
            except Exception as exc:
                wait_time = (attempt + 1) * 3
                print(f"❌ download fail {url}: {exc}; retry {wait_time}s")
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


def main() -> None:
    countries_cache = load_json("test1/countries_cache.json", {})
    history = load_json(STATUS_FILE, {})
    ranking_db = load_json(RANKING_FILE, {})
    blacklist = set(load_lines(BLACKLIST_FILE))
    pinned_list = dedupe_links(load_lines(PINNED_FILE, contains="vless://"))
    deferred = load_lines(DEFERRED_FILE)
    current_base = load_lines(INPUT_FILE)
    external = fetch_external_servers()

    queue = dedupe_links(pinned_list + deferred + external + current_base)
    print(f"📦 pinned={len(pinned_list)} queue={len(queue)}")

    pinned_bases = {p.split("#", 1)[0].strip() for p in pinned_list}

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
    while len(working_for_sub) < MAX_SUB_LINKS and idx < len(queue):
        link = queue[idx]
        idx += 1

        base = link.split("#", 1)[0].strip()
        if base in pinned_bases or base in blacklist:
            continue

        if checked >= MAX_TO_CHECK:
            deferred_next.extend(queue[idx - 1 :])
            break

        if not re.search(r"[a-f0-9\-]{36}@", base):
            continue

        endpoint, host, port = extract_host_port(base)
        if not endpoint or not host or not port:
            continue

        checked += 1
        latency = 0

        print(f"🔍 {checked}/{MAX_TO_CHECK} {host}:{port}", flush=True)

        tried_sni: set[str] = set()
        for cand_sni in extract_sni_candidates(link):
            cand_sni = cand_sni.strip()
            if not cand_sni or cand_sni in tried_sni:
                continue
            tried_sni.add(cand_sni)
            latency = probe_vless_l7(link, cand_sni, timeout=PROBE_TIMEOUT)
            if latency > 0:
                break

        if latency <= 0:
            fallback_sni = extract_sni(link).strip()
            if fallback_sni and fallback_sni not in tried_sni:
                latency = probe_vless_l7(link, fallback_sni, timeout=PROBE_TIMEOUT)

        if latency <= 0:
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
            continue

        sub_link = base
        if "sni=" not in sub_link.lower() and not is_ipv6(host):
            sub_link += ("&" if "?" in sub_link else "?") + f"sni={host}"

        final = rebuild_link_name(sub_link, f"wifi {counter} [{latency}ms]")
        working_for_sub.append(final)
        working_for_base.append(base)
        print(f"✅ {len(working_for_sub)}/{MAX_SUB_LINKS}: {host}:{port} {country} {latency}ms")
        counter += 1

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

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER.strip() + "\n\n" + "\n".join(working_for_sub))

    print(f"🏁 done: sub={len(working_for_sub)} deferred={len(deferred_next)} checked={checked}")

if __name__ == "__main__":
    init_checker_lib()
    main()
