import socket
import re
import os

# ПУТИ - проверьте их еще раз!
INPUT_FILE = 'local/test1/1.txt'
OUTPUT_FILE = 'local/kr/mob/wifi.txt'

def check_server(host, port):
    try:
        # Проверка доступности порта (таймаут 3 секунды)
        with socket.create_connection((host, int(port)), timeout=3):
            return True
    except:
        return False

def main():
    # --- БЛОК ОТЛАДКИ ПУТЕЙ ---
    print("--- Список всех файлов в репозитории ---")
    found_input = False
    for root, dirs, files in os.walk("."):
        for file in files:
            if ".git" not in root:
                path = os.path.join(root, file).lstrip('./')
                print(f"Найден файл: {path}")
                if path == INPUT_FILE:
                    found_input = True
    print("---------------------------------------")

    if not found_input:
        print(f"ОШИБКА: Файл {INPUT_FILE} не найден. Проверьте список выше!")
        return

    # --- ОСНОВНАЯ ЛОГИКА ---
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        links = f.read().splitlines()

    working_links = []
    print(f"Начинаю проверку {len(links)} серверов...")

    for link in links:
        if not link.startswith('vless://'):
            continue
            
        # Ищем host и port в ссылке
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            if check_server(host, port):
                print(f"✅ РАБОТАЕТ: {host}:{port}")
                working_links.append(link)
            else:
                print(f"❌ МЕРТВ: {host}:{port}")

    # Создаем папку, если её нет, и сохраняем результат
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(working_links))
    
    print(f"Готово! Сохранено {len(working_links)} рабочих серверов в {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
