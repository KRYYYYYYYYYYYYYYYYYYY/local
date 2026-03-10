import os
import time
import socket

# Пути к твоим файлам
WIFI_FILE = 'kr/mob/wifi.txt'
DEFERRED_FILE = 'test1/deferred.txt'
INPUT_FILE = 'test1/1.txt'
BLACKLIST_FILE = 'test1/blacklist.txt'
PINNED_FILE = 'test1/pinned.txt'

def add_to_blacklist(link):
    """ Записывает сервер в вечный бан, если его там еще нет """
    clean_link = link.split('#')[0].strip()
    existing_black = set()
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            existing_black = {line.strip() for line in f}
    
    if clean_link not in existing_black:
        with open(BLACKLIST_FILE, 'a') as f:
            f.write(clean_link + "\n")
        print(f"🚫 ОТПРАВЛЕН В БЛОК: {clean_link[:40]}...")

def remove_from_all_files(link):
    """ Удаляет плохой сервер из всех рабочих файлов сразу """
    clean_link = link.split('#')[0].strip()
    files_to_clean = [WIFI_FILE, DEFERRED_FILE, INPUT_FILE]
    
    for file_path in files_to_clean:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Оставляем только те строки, которые НЕ содержат этот сервер
            new_lines = [line for line in lines if clean_link not in line]
            
            if len(lines) != len(new_lines):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                print(f"🗑️ Удален из {file_path}")

def main_monitor():
    start_run = time.time()
    # Работаем 10 минут, делая обход каждую минуту
    while time.time() - start_run < 600:
        print(f"🕵️ Надзиратель вышел на обход: {time.strftime('%H:%M:%S')}")
        
        # Собираем список всех активных серверов для проверки (кроме закрепов)
        active_links = []
        if os.path.exists(WIFI_FILE):
            with open(WIFI_FILE, 'r', encoding='utf-8') as f:
                active_links.extend([line.strip() for line in f if 'vless://' in line])
        
        # Проверяем каждый
        for link in active_links:
            # Вызываем "Мясорубку" (которую мы обсуждали: 3 удара, > 1000мс = смерть)
            if not deep_kill_check(link): 
                print(f"💀 СЕРВЕР СДОХ ИЛИ ТОРМОЗИТ: {link[:40]}...")
                # 3. УДАЛЯЕМ ИЗ ФАЙЛОВ
                remove_from_all_files(link)
                # 4. ЗАПИСЫВАЕМ В БЛОК
                add_to_blacklist(link)
        
        print("☕ Обход завершен. Минута отдыха...")
        time.sleep(60)

if __name__ == "__main__":
    main_monitor()
