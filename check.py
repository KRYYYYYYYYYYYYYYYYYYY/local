import socket
import re

# Настройки
INPUT_FILE = '1.txt'     # Где лежат исходники
OUTPUT_FILE = 'local/kr/mob/wifi.txt' # Куда сохранять результат

def check_server(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            return True
    except:
        return False

def main():
    with open(INPUT_FILE, 'r') as f:
        lines = f.read().splitlines()

    working_links = []
    for link in lines:
        # Извлекаем адрес и порт из vless://... @host:port...
        match = re.search(r'@([\w\.-]+):(\d+)', link)
        if match:
            host, port = match.groups()
            if check_server(host, port):
                working_links.append(link)
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write('\n'.join(working_links))

if __name__ == "__main__":
    main()
