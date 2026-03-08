import socket
import re
import os
import json
import urllib.request

INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Без IPv6 и заблокированных стран)
# profile-update-interval: 2

"""

def is_ipv6(host):
    return ":" in host and not host.startswith('[')

def get_country_code(host):
    """Gets the server's country without installing extra libraries"""
    try:
        # Use the standard urllib library to request IP-API
        with urllib.request.urlopen(f"http://ip-api.com{host}?fields=status,countryCode", timeout=2) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                return data.get('countryCode')
    except:
        pass
    return "Unknown"

def check_server_smart(host, port):
    if is_ipv6(host):
        print(f"⏩ Пропуск IPv6: {host}")
        return False

    # Filter countries for ChatGPT/Gemini
    country = get_country_code(host)
    if country in ['RU', 'CN', 'IR', 'KP']:
        print(f"🚩 Пропуск {country} (ChatGPT/Gemini недоступны): {host}")
        return False

    try:
        ip_address = socket.gethostbyname(host)
        with socket.create_connection((ip_address, int(port)), timeout=2.5):
            return True
    except Exception:
        return False

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    working_links = []
    seen_configs = set()

    print(f"Начинаю умную проверку {len(lines)} строк...")

    for link in lines:
        link = link.strip()
        if not link.startswith('vless://') or link in seen_configs:
            continue
            
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            if check_server_smart(host, port):
                working_links.append(link)
                seen_configs.add(link)
                print(f"✅ ОК: {host}")
            else:
                # We do not output FAIL here, as the details are displayed in check_server_smart
                pass

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(HEADER + '\n'.join(working_links))
    
    print(f"Завершено. Сохранено рабочих: {len(working_links)}")

if __name__ == "__main__":
    main()
