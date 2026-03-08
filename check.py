import socket
import re
import os

# Настройки путей
INPUT_FILE = 'test1/1.txt'
OUTPUT_FILE = 'kr/mob/wifi.txt'

# Ваши сервисные строки (заголовки подписки)
HEADER = """# profile-title: 🏴WIFI🏴
# announce: Подписка для использования на wifi.
# profile-update-interval: 2

"""

def check_server(host, port):
    try:
        # Проверка порта (таймаут 3 секунды)
        with socket.create_connection((host, int(port)), timeout=3):
            return True
    except:
        return False

def main():
    # Проверяем наличие входного файла
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: Файл {INPUT_FILE} не найден.")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    working_links = []
    print(f"Начинаю проверку {len(lines)} строк...")

    for link in lines:
        # Игнорируем пустые строки и комментарии в исходнике
        if not link.startswith('vless://'):
            continue
            
        # Извлекаем host и port
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            if check_server(host, port):
                working_links.append(link)
                print(f"✅ Добавлен: {host}")
            else:
                print(f"❌ Пропущен: {host}")

    # Создаем папки, если их нет
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Записываем всё в итоговый файл
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(HEADER)           # Сначала пишем заголовок
        f.write('\n'.join(working_links)) # Затем рабочие ссылки
    
    print(f"Готово! В файле {OUTPUT_FILE} теперь {len(working_links)} серверов + заголовок.")

if __name__ == "__main__":
    main()
