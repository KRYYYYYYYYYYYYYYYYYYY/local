def main():
    # --- БЛОК ОТЛАДКИ ---
    print("--- Список всех файлов в репозитории ---")
    for root, dirs, files in os.walk("."):
        for file in files:
            if ".git" not in root: # Пропускаем системные файлы
                print(f"Путь для скрипта: {os.path.join(root, file).lstrip('./')}")
    print("---------------------------------------")

    if not os.path.exists(INPUT_FILE):
        print(f"ОШИБКА: Скрипт ищет '{INPUT_FILE}', но не видит его.")
        return
    # --- КОНЕЦ БЛОКА ОТЛАДКИ ---

    with open(INPUT_FILE, 'r') as f:
        # ... дальше ваш старый код ...
