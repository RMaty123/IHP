import os
import sys
import re
import glob
import subprocess

# Podpora barev v terminálu (ANSI escape sekvence)
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Textové barvy
    YELLOW = "\033[93m"       # Žlutá pro cestu nad seznamem
    BLUE = "\033[94m"         # Modrá pro složky a [..]
    BLUE_BOLD = "\033[1;94m"  # Zvýrazněná modrá
    WHITE = "\033[97m"        # Bílá pro soubory
    CYAN = "\033[96m"         # Azurová pro hlavičky a rámečky
    GREEN = "\033[92m"        # Zelená pro [OK] a úspěchy
    GRAY = "\033[90m"         # Šedá pro doplňující info (velikost, tipy)
    RED = "\033[91m"          # Červená pro chyby a varování

def init_terminal_colors():
    """Povolí ANSI barvy ve Windows terminálu."""
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Povolení ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
            h_out = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
            kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        except Exception:
            os.system('')

init_terminal_colors()

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
    if re.match(r'^\d{1,2}:\d{2}:\d{2}:\d{1,3}$', token):
        return True
    if re.match(r'^\d{1,2}:\d{2}:\d{2}\.\d{1,3}$', token):
        return True
    if re.match(r'^\d{1,2}:\d{2}:\d{2}$', token):
        return True
    if re.match(r'^\d{1,2}:\d{2}:\d{1,2}$', token):
        return True
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
    if '.' in time_str:
        parts_dot = time_str.split('.')
        time_str = parts_dot[0] + ":" + parts_dot[1]

    parts = time_str.split(':')
    
    if len(parts) == 4:
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        cs = int(parts[3])
        return f"{h:02d}:{m:02d}:{s:02d}:{cs:02d}"
    elif len(parts) == 3:
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        return f"{h:02d}:{m:02d}:{s:02d}:00"
    elif len(parts) == 2:
        m = int(parts[0])
        s = int(parts[1])
        return f"00:{m:02d}:{s:02d}:00"
    else:
        return "00:00:00:00"

def seconds_to_time_str(seconds: float) -> str:
    """Převede počet sekund (float) na formát hh:mm:ss:setiny."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d}:{cs:02d}"

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

def get_video_duration(file_path: str) -> str:
    """
    Získá celkovou délku videa pomocí ffprobe nebo ffmpeg a vrátí ji ve formátu hh:mm:ss:setiny.
    Pokud selže nebo soubor neexistuje, vrátí 'Neznámá'.
    """
    if not file_path or not os.path.exists(file_path):
        return "Neznámá"
    
    # 1. Pokus přes ffprobe
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            sec = float(res.stdout.strip())
            return seconds_to_time_str(sec)
    except Exception:
        pass

    # 2. Fallback přes ffmpeg -i
    try:
        cmd = ["ffmpeg", "-i", file_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        combined = (res.stderr or "") + (res.stdout or "")
        match = re.search(r'Duration:\s*(\d{2}:\d{2}:\d{2}[\.:]\d{1,3})', combined)
        if match:
            return normalize_time(match.group(1))
    except Exception:
        pass

    return "Neznámá"

def format_clip_name(file_path: str, max_len: int = 12) -> str:
    """
    Zkrátí název souboru klipu pro zobrazení v promptu `ihp (<nazev>) >` na maximálně max_len znaků.
    Zaručuje, že délka vráceného řetězce nepřesáhne max_len.
    """
    if not file_path:
        return "clip"
    
    clean_path = file_path.strip('\'"')
    base_name = os.path.basename(clean_path)
    if not base_name:
        base_name = clean_path

    if len(base_name) <= max_len:
        return base_name
    
    if max_len <= 3:
        return base_name[:max_len]
        
    return base_name[:max_len - 3] + "..."

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
        print(f"{Colors.RED}[CHYBA při hledání]: {e}{Colors.RESET}")
        
    return results

def setup_readline_completion(candidates: list = None):
    """Nastaví doplňování přes readline, pokud je dostupné."""
    try:
        import readline
        def complete_fn(text, state):
            options = []
            if candidates:
                options = [c for c in candidates if c.lower().startswith(text.lower())]
            if not options:
                expanded = os.path.expanduser(text)
                pattern = expanded + '*'
                matches = glob.glob(pattern)
                for match in matches:
                    if os.path.isdir(match):
                        options.append(match + os.sep)
                    else:
                        options.append(match)
            if state < len(options):
                return options[state]
            return None
            
        readline.set_completer_delims(' \t\n;')
        readline.set_completer(complete_fn)
        readline.parse_and_bind('tab: complete')
    except Exception:
        pass

def custom_tab_input(prompt_text: str, suggestions: list) -> str:
    """
    Načte uživatelský vstup z terminálu s podporou klávesy Tab pro okamžité doplnění prvního
    navrženého souboru/položky nebo shody podle začátku textu.
    Na Windows využívá msvcrt pro bezprostřední odchycení Tabulátoru.
    """
    try:
        import msvcrt
        if sys.stdin.isatty():
            print(prompt_text, end='', flush=True)
            buffer = []
            tab_index = 0
            last_was_tab = False
            matching_cache = []

            while True:
                ch = msvcrt.getwch()

                # Enter (\r nebo \n)
                if ch in ('\r', '\n'):
                    print()
                    return "".join(buffer)

                # Ctrl+C
                elif ch == '\x03':
                    print()
                    raise KeyboardInterrupt

                # Tab (\t) -> doplnit první navržený soubor nebo cyklovat shody
                elif ch == '\t':
                    current_text = "".join(buffer)
                    if not last_was_tab:
                        tab_index = 0
                        if not current_text:
                            matching_cache = list(suggestions)
                        else:
                            matching_cache = [s for s in suggestions if s.lower().startswith(current_text.lower())]
                            if not matching_cache:
                                matching_cache = [s for s in suggestions if current_text.lower() in s.lower()]

                    if matching_cache:
                        chosen = matching_cache[tab_index % len(matching_cache)]
                        tab_index += 1
                        back_len = len(buffer)
                        print('\b' * back_len + ' ' * back_len + '\b' * back_len, end='', flush=True)
                        buffer = list(chosen)
                        print(chosen, end='', flush=True)
                        last_was_tab = True
                    continue

                # Backspace (\x08 nebo \x7f)
                elif ch in ('\x08', '\x7f'):
                    last_was_tab = False
                    if buffer:
                        buffer.pop()
                        print('\b \b', end='', flush=True)
                    continue

                # Speciální klávesy (šipky, F-klávesy)
                elif ch in ('\x00', '\xe0'):
                    msvcrt.getwch()
                    continue

                # Běžný znak
                else:
                    last_was_tab = False
                    buffer.append(ch)
                    print(ch, end='', flush=True)
    except Exception:
        pass

    # Fallback na standardní input
    setup_readline_completion(suggestions)
    try:
        return input(prompt_text)
    except (KeyboardInterrupt, EOFError):
        raise

def interactive_file_picker(start_dir: str = ".") -> str:
    """
    Interaktivní a barevný terminálový průzkumník pro výběr souboru.
    Barevné schéma:
      - Žlutá: Cesta nad seznamem položek
      - Modrá: Složky a [..]
      - Bílá: Soubory (s velikostmi v šedé)
      - Tabulátor: Okamžité doplnění prvního navrženého souboru
    
    Vrací: vybraná_cesta (str) nebo None při zrušení.
    """
    current_dir = os.path.abspath(start_dir)

    print("\n" + f"{Colors.CYAN}{'=' * 64}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD} === ASISTENT PRO VÝBĚR SOUBORU KLIPU ==={Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 64}{Colors.RESET}")
    print(f" {Colors.GRAY}Tip: Stiskněte {Colors.WHITE}[Tab]{Colors.GRAY} pro okamžité doplnění prvního souboru.{Colors.RESET}")
    print(f"      {Colors.GRAY}Zadejte číslo položky, napište {Colors.WHITE}'search <text>'{Colors.GRAY} nebo {Colors.WHITE}'q'{Colors.GRAY} pro zrušení.{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 64}{Colors.RESET}")

    while True:
        try:
            entries = os.listdir(current_dir)
        except Exception as e:
            print(f"{Colors.RED}[CHYBA] Nelze načíst složku '{current_dir}': {e}{Colors.RESET}")
            current_dir = os.path.abspath(".")
            try:
                entries = os.listdir(current_dir)
            except Exception:
                entries = []

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
        
        # 1. ŽLUTÁ CESTA NAD SEZNAMEM
        print(f"\n{Colors.YELLOW}{Colors.BOLD}📂 Cesta: {current_dir}{Colors.RESET}")
        print(f"{Colors.YELLOW}{'-' * 64}{Colors.RESET}")
        
        idx = 1
        parent_dir = os.path.dirname(current_dir)
        has_parent = parent_dir and parent_dir != current_dir

        # 2. MODRÉ SLOŽKY (VČETNĚ ..)
        if has_parent:
            print(f"  {Colors.BLUE_BOLD}[..] [NAHORU] .. (Přejít o úroveň výš){Colors.RESET}")

        for d in dirs:
            print(f"  {Colors.BLUE_BOLD}[{idx:>2}] [SLOŽKA] {d}/{Colors.RESET}")
            items_list.append(('dir', os.path.join(current_dir, d), d))
            idx += 1

        # 3. BÍLÉ SOUBORY
        for f in media_files:
            f_path = os.path.join(current_dir, f)
            size_str = get_file_size_str(f_path)
            size_display = f" {Colors.GRAY}({size_str}){Colors.RESET}" if size_str else ""
            print(f"  {Colors.WHITE}[{idx:>2}] [KLIP]   {f}{Colors.RESET}{size_display}")
            items_list.append(('file', f_path, f))
            idx += 1

        # Ostatní soubory (pokud nejsou mediální soubory)
        if len(media_files) == 0 and other_files:
            print(f"  {Colors.GRAY}--- Ostatní soubory ---{Colors.RESET}")
            for f in other_files[:15]:
                f_path = os.path.join(current_dir, f)
                print(f"  {Colors.WHITE}[{idx:>2}] [SOUBOR] {f}{Colors.RESET}")
                items_list.append(('file', f_path, f))
                idx += 1

        if not dirs and not media_files and not other_files:
            print(f"  {Colors.GRAY}(Tato složka je prázdná){Colors.RESET}")

        # Příprava návrhů pro klávesu Tab (soubory první, pak složky)
        tab_candidates = []
        for f in media_files:
            tab_candidates.append(f)
        for d in dirs:
            tab_candidates.append(d)
        for i in range(1, len(items_list) + 1):
            tab_candidates.append(str(i))

        print(f"{Colors.YELLOW}{'-' * 64}{Colors.RESET}")
        try:
            prompt_str = f"Vyberte [{Colors.CYAN}Tab{Colors.RESET}=první soubor / číslo / cesta / 'search' / 'q']: "
            choice = custom_tab_input(prompt_str, tab_candidates).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.GRAY}[Výběr zrušen]{Colors.RESET}")
            return None

        if not choice:
            continue

        choice_lower = choice.lower()

        # Zrušení výběru
        if choice_lower in ['q', 'quit', 'exit', 'cancel', 'zrusit']:
            print(f"{Colors.GRAY}[Výběr souboru zrušen]{Colors.RESET}")
            return None

        # Přechod o úroveň výš
        if choice == '..':
            if has_parent:
                current_dir = parent_dir
            else:
                print(f"{Colors.GRAY}[INFO] Již jste v kořenovém adresáři.{Colors.RESET}")
            continue

        # Vyhledávání souborů
        if choice_lower.startswith('search ') or choice_lower.startswith('hledat ') or choice_lower.startswith('f '):
            query = choice.split(' ', 1)[1].strip()
            print(f"\n{Colors.CYAN}[HLEDÁNÍ] Hledám '{query}' v aktuální složce a podsložkách...{Colors.RESET}")
            search_results = search_media_files(current_dir, query)
            
            if not search_results:
                print(f"{Colors.YELLOW}[INFO] Žádné mediální soubory odpovídající '{query}' nebyly nalezeny.{Colors.RESET}")
                continue
                
            print(f"{Colors.GREEN}Nalezeno {len(search_results)} výsledků:{Colors.RESET}")
            for s_idx, (rel_p, full_p, _) in enumerate(search_results, start=1):
                size_str = get_file_size_str(full_p)
                print(f"  {Colors.WHITE}[{s_idx:>2}] [KLIP] {rel_p}{Colors.RESET} {Colors.GRAY}({size_str}){Colors.RESET}")
                
            print(f"  {Colors.GRAY}[0] Zpět do prohlížeče složek{Colors.RESET}")
            try:
                s_choice = custom_tab_input(f"Vyberte číslo souboru [1-{len(search_results)}]: ", [str(i) for i in range(1, len(search_results) + 1)]).strip()
                if s_choice.isdigit():
                    s_num = int(s_choice)
                    if 1 <= s_num <= len(search_results):
                        return search_results[s_num - 1][1]
            except (KeyboardInterrupt, EOFError):
                pass
            continue

        # Číselný výběr
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(items_list):
                item_type, item_path, item_name = items_list[num - 1]
                if item_type == 'dir':
                    current_dir = item_path
                    continue
                else:
                    return item_path
            else:
                print(f"{Colors.RED}[CHYBA] Neplatné číslo volby '{choice}'.{Colors.RESET}")
                continue

        # Přímé zadání cesty / názvu
        clean_input = choice.strip('\'"')

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
                return found_target
        else:
            print(f"{Colors.YELLOW}[VAROVÁNÍ] Cesta '{clean_input}' nebyla nalezena na disku.{Colors.RESET}")
            try:
                ans = input("Chcete přesto použít tuto cestu? (y/n): ").strip().lower()
                if ans == 'y':
                    return clean_input
            except (KeyboardInterrupt, EOFError):
                return None

def handle_add(editor, args: list) -> bool:
    """
    Hlavní obslužná funkce pro příkaz 'add'.
    Přijímá pouze cestu (bez časových parametrů) nebo spustí asistenta s podporou Tabulátoru.
    
    Po výběru souboru zjistí jeho přesnou délku a vypíše ji ve formátu HH:MM:ss:setiny.
    """
    file_path = None
    if args:
        file_path = " ".join(args).strip('\'"')

    # Pokud nebyla zadána cesta, spustíme barevného asistenta
    if not file_path:
        file_path = interactive_file_picker()
        if not file_path:
            return False

    file_path = file_path.strip('\'"')
    
    # Kontrola existence
    if not os.path.exists(file_path):
        norm_path = os.path.normpath(file_path)
        if not os.path.exists(norm_path):
            print(f"\n{Colors.YELLOW}[VAROVÁNÍ] Soubor '{file_path}' nebyl nalezen na disku!{Colors.RESET}")
            print("1. Spustit asistenta pro výběr souboru")
            print("2. Použít zadanou cestu i přes varování")
            print("3. Zrušit")
            try:
                opt = input("Vyberte možnost [1/2/3] (výchozí 1): ").strip()
            except (KeyboardInterrupt, EOFError):
                return False
                
            if opt in ['1', '']:
                file_path = interactive_file_picker()
                if not file_path:
                    return False
            elif opt == '2':
                pass
            else:
                print(f"{Colors.GRAY}[Příkaz 'add' zrušen]{Colors.RESET}")
                return False

    # Zjištění délky videa
    print(f"{Colors.GRAY}[INFO] Zjišťuji délku videa...{Colors.RESET}")
    duration = get_video_duration(file_path)
    default_out = duration if duration != "Neznámá" else None

    # Nastavení aktuálního klipu v editoru
    editor.current_clip = {
        "path": file_path,
        "in": "00:00:00:00",
        "out": default_out,
        "duration": duration
    }
    
    clip_display = format_clip_name(file_path, max_len=12)
    
    # Přehledný rámeček po výběru souboru se zjištěnou délkou v HH:MM:ss:setiny
    print()
    print(f"{Colors.GREEN}{'=' * 64}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD} [KLIP] Vybrán soubor: {os.path.basename(file_path)}{Colors.RESET}")
    print(f"        {Colors.WHITE}Cesta:        {file_path}{Colors.RESET}")
    print(f"        {Colors.YELLOW}{Colors.BOLD}Délka videa:  {duration}{Colors.RESET} {Colors.GRAY}(HH:MM:ss:setiny){Colors.RESET}")
    print(f"{Colors.GREEN}{'-' * 64}{Colors.RESET}")
    print(f" {Colors.CYAN}Příkazy pro editaci klipu:{Colors.RESET}")
    print(f"   {Colors.WHITE}start <čas>{Colors.RESET} - Nastaví začátek (výchozí: 00:00:00:00)")
    print(f"   {Colors.WHITE}stop <čas>{Colors.RESET}  - Nastaví konec   (aktuálně: {default_out or 'celé video'})")
    print(f"   {Colors.WHITE}end{Colors.RESET}         - Uloží klip na časovou osu a vrátí se do menu")
    print(f"   {Colors.WHITE}help{Colors.RESET}        - Zobrazí nápovědu")
    print(f"{Colors.GREEN}{'=' * 64}{Colors.RESET}")
    print()
    return True
