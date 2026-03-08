import socket
import re
import os

INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'

HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для на wifi! (Только IPv4 и проверенные порты)
# profile-update-interval: 2

"""

def is_ipv6(host):
    """Проверяет, является ли адрес IPv6 (содержит двоеточия)"""
    return ":" in host and not host.startswith('[') # Упрощенная проверка

def check_server_smart(host, port):
    # 1. Сразу отсекаем явные IPv6, если они не обернуты в скобки (часто не работают)
    if is_ipv6(host):
        print(f"⏩ Пропуск IPv6: {host}")
        return False

    try:
        # 2. Пытаемся определить IP (DNS Check)
        ip_address = socket.gethostbyname(host)
        
        # 3. Проверка порта с коротким таймаутом
        with socket.create_connection((ip_address, int(port)), timeout=2.5):
            return True
    except Exception:
        return False

def main():
    if not os.path.exists(INPUT_FILE): return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    working_links = []
    seen_configs = set() # Для удаления дубликатов

    for link in lines:
        if not link.startswith('vless://') or link in seen_configs:
            continue
            
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            # Используем "умную" проверку
            if check_server_smart(host, port):
                working_links.append(link)
                seen_configs.add(link)
                print(f"✅ ОК: {host}")
            else:
                print(f"❌ FAIL: {host}")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(HEADER + '\n'.join(working_links))

if __name__ == "__main__":
    main()
