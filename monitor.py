import socket, time, os, ssl, re, json

# Твои файлы
WIFI_FILE = 'kr/mob/wifi.txt'
DEFERRED_FILE = 'test1/deferred.txt'
PINNED_FILE = 'test1/pinned.txt'
BLACKLIST_FILE = 'test1/blacklist.txt'

def is_pinned(link):
    if not os.path.exists(PINNED_FILE): return False
    with open(PINNED_FILE, 'r') as f:
        pinned = f.read()
    return link.split('#')[0] in pinned

def deep_kill_check(link):
    """ Интенсивная проверка: 3 удара. Если хоть один > 1000мс = СМЕРТЬ """
    if is_pinned(link): return True # ИММУНИТЕТ ЗАКРЕПОВ
    
    # Извлекаем хост и порт (твоя функция extract_host_port)
    # ... (логика извлечения) ...
    
    for _ in range(3):
        try:
            start = time.time()
            with socket.create_connection((host, int(port)), timeout=3.0):
                lat = (time.time() - start) * 1000
                if lat > 1000: return False # Тормоз — в бан
            time.sleep(1) # Пауза между ударами
        except:
            return False # Упал — в бан
    return True

def main_monitor():
    start_run = time.time()
    # Цикл работает 10 минут (в пределах одного запуска Actions)
    while time.time() - start_run < 600: 
        print(f"🕵️ Надзиратель вышел на обход: {time.strftime('%H:%M:%S')}")
        
        # 1. Проверяем wifi.txt и deferred.txt
        # 2. Если deep_kill_check == False:
        #    - Удаляем из файла
        #    - Дописываем в blacklist.txt
        
        time.sleep(60) # Минута тишины и снова в бой

if __name__ == "__main__":
    main_monitor()

