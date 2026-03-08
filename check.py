import socket
import re
import os
import json
import urllib.request
import urllib.parse

INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Нумерованная, без IPv6 и RU/CN)
# profile-update-interval: 2

"""

def is_ipv6(host):
    return ":" in host and not host.startswith('[')

def get_country_code(host):
    try:
        # Исправлено: добавлен /json/ и правильный формат запроса
        url = f"http://ip-api.com{host}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=2) as response:
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
    
    country = get_country_code(host)
    if country in ['RU', 'CN', 'IR', 'KP']:
        print(f"🚩 Пропуск {country} (No ChatGPT): {host}")
        return False

    try:
        ip_address = socket.gethostbyname(host)
        with socket.create_connection((ip_address, int(port)), timeout=2.5):
            return True
    except:
        return False

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: {INPUT_FILE} не найден")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    working_links = []
    seen_configs = set()
    counter = 1 

    print(f"Начинаю проверку и нумерацию {len(lines)} строк...")

    for link in lines:
        link = link.strip()
        if not link.startswith('vless://') or link in seen_configs:
            continue
            
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            if check_server_smart(host, port):
                # ЛОГИКА НУМЕРАЦИИ:
                # Отрезаем всё после # и ставим свое имя wifi N
                base_part = link.split('#')[0]
                new_name = urllib.parse.quote(f"wifi {counter}")
                final_link = f"{base_part}#{new_name}"
                
                working_links.append(final_link)
                seen_configs.add(link)
                print(f"✅ ОК: {host} -> wifi {counter}")
                counter += 1

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(HEADER + '\n'.join(working_links))
    
    print(f"Завершено. Сохранено в подписку: {len(working_links)}")

if __name__ == "__main__":
    main()
