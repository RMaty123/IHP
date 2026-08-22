import os
import sys
import re
import glob

# Podporované přípony mediálních souborů
MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv', '.wmv', '.m4v', '.ts',
    '.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.opus', '.wma'
}

def is_time_format(token: str) -> bool:
    """
    Zkontroluje, zda token odpovídá časovému formátu.
    Podporuje:
      - hh:mm:ss:setiny (např. 00:01:23:45)
      - hh:mm:ss.setiny (např. 00:01:23.45)
      - hh:mm:ss (např. 00:01:23)
      - mm:ss:setiny nebo mm:ss (např. 01:23:45)
    """
    if not token or not isinstance(token, str):
        return False
    
    token = token.strip()
    
    # 4 části: hh:mm:ss:setiny (např. 00:01:23:45)
    if re.match(r'^\d{1,2}:\d{2}:\d{2}:\d{1,3}$', token):
        return True
    # hh:mm:ss.setiny (např. 00:01:23.45)
    if re.match(r'^\d{1,2}:\d{2}:\d{2}\.\d{1,3}$', token):
        return True
    # 3 části: hh:mm:ss (např. 00:01:23)
    if re.match(r'^\d{1,2}:\d{2}:\d{2}$', token):
        return True
    # mm:ss:setiny (např. 01:23:45)
    if re.match(r'^\d{1,2}:\d{2}:\d{1,2}$', token):
        return True
    # mm:ss (např. 01:23)
    if re.match(r'^\d{1,2}:\d{2}$', token):
        return True
        
    return False

def normalize_time(time_str: str) -> str:
    """
    Normalizuje časový řetězec do standardního formátu hh:mm:ss:setiny (např. 00:01:23:45).
    """
    if not time_str or not isinstance(time_str, str):
        return "00:00:00:00"
    
    time_str = time_str.strip()
    # Nahradit tečku za poslední dvojtečku, pokud byla použita tečka
    if '.' in time_str:
        parts_dot = time_str.split('.')
        time_str = parts_dot[0] + ":" + parts_dot[1]

    parts = time_str.split(':')
    
    if len(parts) == 4:
        # hh:mm:ss:setiny
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        cs = int(parts[3])
        return f"{h:02d}:{m:02d}:{s:02d}:{cs:02d}"
    elif len(parts) == 3:
        # hh:mm:ss -> hh:mm:ss:00
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        return f"{h:02d}:{m:02d}:{s:02d}:00"
    elif len(parts) == 2:
        # mm:ss -> 00:mm:ss:00
        m = int(parts[0])
        s = int(parts[1])
        return f"00:{m:02d}:{s:02d}:00"
    else:
        return "00:00:00:00"

def time_to_ffmpeg(time_str: str) -> str:
    """
    Převede čas ve formátu hh:mm:ss:setiny na formát akceptovaný FFmpeg (hh:mm:ss.setiny).
    Pokud je čas 00:00:00:00, vrátí '00:00:00'.
    """
    if not time_str:
        return "00:00:00"
    
    norm = normalize_time(time_str)
    if norm == "00:00:00:00":
        return "00:00:00"
        
    parts = norm.split(':')
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"
    return norm

def format_clip_name(file_path: str, max_len: int = 12) -> str:
    """
    Zkrátí název souboru klipu pro zobrazení v promptu `ihp (<nazev>) >` na maximálně max_len znaků.
    Zaručuje, že délka vráceného řetězce nepřesáhne max_len.
    """
    if not file_path:
        return "clip"
    
    # Získání samotného názvu souboru (basename)
    clean_path = file_path.strip('\'"')
    base_name = os.path.basename(clean_path)
    if not base_name:
        base_name = clean_path

    if len(base_name) <= max_len:
        return base_name
    
    if max_len <= 3:
        return base_name[:max_len]
        
    return base_name[:max_len - 3] + "..."

def parse_add_arguments(args: list) -> tuple:
    """
    Flexibilně zpracuje argumenty příkazu add.
    Rozpozná:
      1. add <cesta> <cas>
      2. add <cas> <cesta>
      3. add <cesta> (čas výchozí 00:00:00:00)
      4. add <cas> (cesta None -> interaktivní výběr)
      5. add (žádné argumenty -> cesta None, čas 00:00:00:00)
      6. Cesty s mezerami (např. add 00:01:00:00 C:\\Moje Videa\\dovolena 2026.mp4)
      7. Absolutní i relativní cesty, s uvozovkami i bez.
    
    Vrací: (file_path, start_time)
    """
    if not args:
        return (None, "00:00:00:00")
    
    # 1. Zkontrolujeme, zda je v argumentech čas
    # Možnost A: První argument je čas
    if len(args) >= 1 and is_time_format(args[0]):
        start_time = normalize_time(args[0])
        remaining = args[1:]
        if remaining:
            # Zbytek je cesta (může obsahovat mezery)
            file_path = " ".join(remaining).strip('\'"')
        else:
            file_path = None
        return (file_path, start_time)
    
    # Možnost B: Poslední argument je čas
    if len(args) >= 2 and is_time_format(args[-1]):
        start_time = normalize_time(args[-1])
        file_path = " ".join(args[:-1]).strip('\'"')
        return (file_path, start_time)
    
    # Možnost C: Žádný argument není čas -> vše je cesta, čas je výchozí
    start_time = "00:00:00:00"
    file_path = " ".join(args).strip('\'"')
    return (file_path, start_time)

def get_file_size_str(filepath: str) -> str:
    """Vrátí lidsky čitelnou velikost souboru."""
    try:
        size = os.path.getsize(filepath)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    except Exception:
        return ""

def search_media_files(directory: str, query: str = "", max_results: int = 25) -> list:
    """
    Vyhledá mediální soubory v daném adresáři a podadresářích podle dotazu.
    """
    results = []
    query_lower = query.lower()
    
    try:
        for root, dirs, files in os.walk(directory):
            # Ignorovat skryté složky jako .git
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in MEDIA_EXTENSIONS or not query_lower:
                    if query_lower in file.lower():
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, directory)
                        results.append((rel_path, full_path, False))
                        if len(results) >= max_results:
                            return results
    except Exception as e:
        print(f"[CHYBA při hledání]: {e}")
        
    return results

def setup_readline_completion():
    """Pokusí se nastavit doplňování cest pomocí tabulátoru, pokud je dostupné."""
    try:
        import readline
        def complete_path(text, state):
            # Rozšíření ~ a globbing pro doplňování cest
            expanded = os.path.expanduser(text)
            pattern = expanded + '*'
            matches = glob.glob(pattern)
            results = []
            for match in matches:
                if os.path.isdir(match):
                    results.append(match + os.sep)
                else:
                    results.append(match)
            if state < len(results):
                return results[state]
            return None
            
        readline.set_completer_delims(' \t\n;')
        readline.set_completer(complete_path)
        readline.parse_and_bind('tab: complete')
    except Exception:
        pass

def interactive_file_picker(start_dir: str = ".", time_str: str = "00:00:00:00") -> tuple:
    """
    Interaktivní terminálový průzkumník a asistent pro výběr souboru.
    Umožňuje:
      - Zobrazit soubory a složky s čísly pro rychlý výběr
      - Procházet složky (zadáním čísla složky nebo ..)
      - Hledat soubory (příkaz search <text> nebo f <text>)
      - Přímo zadat libovolnou absolutní či relativní cestu
      - Zrušit výběr (q / cancel)
    
    Vrací: (vybraná_cesta, cas) nebo (None, cas) při zrušení
    """
    setup_readline_completion()
    current_dir = os.path.abspath(start_dir)

    print("\n" + "=" * 60)
    print(" === ASISTENT PRO VÝBĚR SOUBORU KLIPU ===")
    print("=" * 60)
    print(f" Nastavený počáteční čas: {time_str}")
    print(" Tip: Napište číslo položky, zadejte/vložte cestu,")
    print("      napište 'search <text>' pro hledání, nebo 'q' pro zrušení.")
    print("=" * 60)

    while True:
        try:
            entries = os.listdir(current_dir)
        except Exception as e:
            print(f"[CHYBA] Nelze načíst složku '{current_dir}': {e}")
            current_dir = os.path.abspath(".")
            try:
                entries = os.listdir(current_dir)
            except Exception:
                entries = []

        # Třídění: nejdříve složky, pak video/audio soubory, pak ostatní
        dirs = []
        media_files = []
        other_files = []

        for item in sorted(entries, key=lambda s: s.lower()):
            if item.startswith('.'):
                continue
            item_path = os.path.join(current_dir, item)
            if os.path.isdir(item_path):
                dirs.append(item)
            else:
                ext = os.path.splitext(item)[1].lower()
                if ext in MEDIA_EXTENSIONS:
                    media_files.append(item)
                else:
                    other_files.append(item)

        items_list = []
        
        print(f"\n[SLOŽKA] Aktuální složka: {current_dir}")
        print("-" * 60)
        
        idx = 1
        # Volba pro přechod výš
        parent_dir = os.path.dirname(current_dir)
        has_parent = parent_dir and parent_dir != current_dir
        if has_parent:
            print(f"  [..] [NAHORU] Přejít o úroveň výš (..)")

        # Výpis složek
        for d in dirs:
            print(f"  [{idx:>2}] [SLOŽKA] {d}/")
            items_list.append(('dir', os.path.join(current_dir, d), d))
            idx += 1

        # Výpis mediálních souborů
        for f in media_files:
            f_path = os.path.join(current_dir, f)
            size_str = get_file_size_str(f_path)
            size_display = f"({size_str})" if size_str else ""
            print(f"  [{idx:>2}] [KLIP]   {f} {size_display}")
            items_list.append(('file', f_path, f))
            idx += 1

        # Výpis ostatních souborů (pokud jich není příliš mnoho)
        if len(media_files) == 0 and other_files:
            print("  --- Ostatní soubory ---")
            for f in other_files[:15]:
                f_path = os.path.join(current_dir, f)
                print(f"  [{idx:>2}] [SOUBOR] {f}")
                items_list.append(('file', f_path, f))
                idx += 1

        if not dirs and not media_files and not other_files:
            print("  (Tato složka je prázdná)")

        print("-" * 60)
        try:
            choice = input("Vyberte [číslo / cesta / 'search <text>' / 'q']: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[Výběr zrušen]")
            return (None, time_str)

        if not choice:
            continue

        choice_lower = choice.lower()

        # Zrušení
        if choice_lower in ['q', 'quit', 'exit', 'cancel', 'zrusit']:
            print("[Výběr souboru zrušen]")
            return (None, time_str)

        # Přechod o úroveň výš
        if choice == '..':
            if has_parent:
                current_dir = parent_dir
            else:
                print("[INFO] Již jste v kořenovém adresáři.")
            continue

        # Vyhledávání
        if choice_lower.startswith('search ') or choice_lower.startswith('hledat ') or choice_lower.startswith('f '):
            query = choice.split(' ', 1)[1].strip()
            print(f"\n[HLEDÁNÍ] Hledám '{query}' v aktuální složce a podsložkách...")
            search_results = search_media_files(current_dir, query)
            
            if not search_results:
                print(f"[INFO] Žádné mediální soubory odpovídající '{query}' nebyly nalezeny.")
                continue
                
            print(f"Nalezeno {len(search_results)} výsledků:")
            for s_idx, (rel_p, full_p, _) in enumerate(search_results, start=1):
                size_str = get_file_size_str(full_p)
                print(f"  [{s_idx:>2}] [KLIP] {rel_p} ({size_str})")
                
            print("  [0] Zpět do prohlížeče složek")
            try:
                s_choice = input("Vyberte číslo souboru [1-{0}]: ".format(len(search_results))).strip()
                if s_choice.isdigit():
                    s_num = int(s_choice)
                    if 1 <= s_num <= len(search_results):
                        chosen_full = search_results[s_num - 1][1]
                        return (chosen_full, time_str)
            except (KeyboardInterrupt, EOFError):
                pass
            continue

        # Číselný výběr z aktuální složky
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(items_list):
                item_type, item_path, item_name = items_list[num - 1]
                if item_type == 'dir':
                    current_dir = item_path
                    continue
                else:
                    return (item_path, time_str)
            else:
                print(f"[CHYBA] Neplatné číslo volby '{choice}'.")
                continue

        # Přímé zadání cesty (relativní nebo absolutní)
        clean_input = choice.strip('\'"')
        
        # Kontrola, zda nezadal i čas (např. "video.mp4 00:01:00:00" nebo "00:01:00:00 video.mp4")
        parts = clean_input.split()
        if len(parts) > 1:
            p_path, p_time = parse_add_arguments(parts)
            if p_path:
                clean_input = p_path
            if p_time and p_time != "00:00:00:00":
                time_str = p_time

        # Zkouška absolutní cesty nebo cesty relativní k aktuální složce
        candidates = [
            clean_input,
            os.path.join(current_dir, clean_input),
            os.path.abspath(clean_input)
        ]
        
        found_target = None
        for cand in candidates:
            if os.path.exists(cand):
                found_target = cand
                break
                
        if found_target:
            if os.path.isdir(found_target):
                current_dir = os.path.abspath(found_target)
                continue
            else:
                return (found_target, time_str)
        else:
            print(f"[VAROVÁNÍ] Cesta '{clean_input}' neexistuje.")
            try:
                ans = input("Chcete přesto použít tuto cestu? (y/n): ").strip().lower()
                if ans == 'y':
                    return (clean_input, time_str)
            except (KeyboardInterrupt, EOFError):
                return (None, time_str)

def handle_add(editor, args: list) -> bool:
    """
    Hlavní obslužná funkce pro příkaz 'add'.
    Zpracuje argumenty, spustí asistenta při potřebě a nastaví editor.current_clip.
    
    Vrací True, pokud byl klip úspěšně otevřen, jinak False.
    """
    file_path, start_time = parse_add_arguments(args)

    # Pokud nebyla zadána cesta, spustíme interaktivního asistenta
    if not file_path:
        file_path, start_time = interactive_file_picker(time_str=start_time)
        if not file_path:
            # Uživatel zrušil výběr
            return False

    # Ověření existence cesty (podpora absolutních i relativních cest)
    file_path = file_path.strip('\'"')
    
    # Kontrola existence
    if not os.path.exists(file_path):
        norm_path = os.path.normpath(file_path)
        if not os.path.exists(norm_path):
            print(f"\n[VAROVÁNÍ] Soubor '{file_path}' nebyl nalezen na disku!")
            print("1. Spustit asistenta pro vyhledání souboru")
            print("2. Použít zadanou cestu i přes varování")
            print("3. Zrušit")
            try:
                opt = input("Vyberte možnost [1/2/3] (výchozí 1): ").strip()
            except (KeyboardInterrupt, EOFError):
                return False
                
            if opt in ['1', '']:
                file_path, start_time = interactive_file_picker(time_str=start_time)
                if not file_path:
                    return False
            elif opt == '2':
                pass  # Ponechat zadanou cestu
            else:
                print("[Příkaz 'add' zrušen]")
                return False

    # Nastavení aktuálního klipu v editoru
    editor.current_clip = {
        "path": file_path,
        "in": start_time,
        "out": None
    }
    
    clip_display = format_clip_name(file_path, max_len=12)
    print(f"[OK] Otevřen klip '{file_path}' (Start: {start_time}).")
    print(f"     Nyní jste v režimu klipu: ihp ({clip_display}) >")
    print("     Příkazy: 'cutout <čas>' pro nastavení konce, 'end' pro přidání na časovou osu.")
    return True
