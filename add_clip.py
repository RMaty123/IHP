import os
import sys
import re
import glob
import subprocess

# Terminal color support (ANSI escape sequences)
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Text colors
    YELLOW = "\033[93m"       # Yellow for path header above directory list
    BLUE = "\033[94m"         # Blue for directories and [..]
    BLUE_BOLD = "\033[1;94m"  # Bold blue
    WHITE = "\033[97m"        # White for files
    CYAN = "\033[96m"         # Cyan for headers and borders
    GREEN = "\033[92m"        # Green for [OK] and success messages
    GRAY = "\033[90m"         # Gray for secondary info (file size, hints)
    RED = "\033[91m"          # Red for errors and warnings

def init_terminal_colors():
    """Enable ANSI colors in Windows terminal."""
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
            h_out = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
            kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        except Exception:
            os.system('')

init_terminal_colors()

# Supported media (video and audio) file extensions
MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv', '.wmv', '.m4v', '.ts',
    '.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.opus', '.wma'
}

def is_valid_media_file(file_path: str) -> tuple:
    """
    Validate that the file is a supported video or audio format.
    Returns: (is_valid: bool, reason: str)
    """
    if not file_path:
        return False, "No path provided."
        
    ext = os.path.splitext(file_path)[1].lower()
    if not ext:
        return False, f"File '{os.path.basename(file_path)}' has no file extension."
        
    if ext not in MEDIA_EXTENSIONS:
        return False, f"Extension '{ext}' is not a supported media format (supported: {', '.join(sorted(MEDIA_EXTENSIONS)[:7])}...)."
        
    return True, "OK"

def is_time_format(token: str) -> bool:
    """
    Check if the token matches a valid time format.
    Supports:
      - hh:mm:ss:centiseconds (e.g. 00:01:23:45)
      - hh:mm:ss.centiseconds (e.g. 00:01:23.45)
      - hh:mm:ss (e.g. 00:01:23)
      - mm:ss:centiseconds or mm:ss (e.g. 01:23:45)
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
    Normalize time string to standard format hh:mm:ss:centiseconds (e.g. 00:01:23:45).
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
    """Convert float seconds to hh:mm:ss:centiseconds format."""
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

def time_to_seconds(time_str: str) -> float:
    """
    Convert hh:mm:ss:centiseconds string to total seconds (float).
    Raises ValueError if format is invalid.
    """
    if not time_str or not is_time_format(time_str):
        raise ValueError(f"Invalid time format: '{time_str}'")
    
    norm = normalize_time(time_str)
    parts = norm.split(':')
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2])
    cs = int(parts[3]) if len(parts) > 3 else 0
    return h * 3600.0 + m * 60.0 + s + (cs / 100.0)

def time_to_ffmpeg(time_str: str) -> str:
    """
    Convert hh:mm:ss:centiseconds to FFmpeg compatible format (hh:mm:ss.centiseconds).
    Returns '00:00:00' if zero.
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
    Retrieve video duration using ffprobe or ffmpeg, formatted as hh:mm:ss:centiseconds.
    Returns 'Unknown' if probe fails.
    """
    if not file_path or not os.path.exists(file_path):
        return "Unknown"
    
    # 1. Try ffprobe
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

    # 2. Fallback to ffmpeg -i
    try:
        cmd = ["ffmpeg", "-i", file_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        combined = (res.stderr or "") + (res.stdout or "")
        match = re.search(r'Duration:\s*(\d{2}:\d{2}:\d{2}[\.:]\d{1,3})', combined)
        if match:
            return normalize_time(match.group(1))
    except Exception:
        pass

    return "Unknown"

def format_clip_name(file_path: str, max_len: int = 12) -> str:
    """
    Truncate clip file name for display in prompt `ihp (<name>) >` to at most max_len characters.
    Guarantees length <= max_len.
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
    """Return human-readable file size."""
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
    Search for media files in the given directory and subdirectories by query.
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
        print(f"{Colors.RED}[ERROR during search]: {e}{Colors.RESET}")
        
    return results

def setup_readline_completion(candidates: list = None):
    """Configure tab autocompletion via readline if available."""
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
    Read user input from terminal with Tab autocompletion support.
    On Windows, uses msvcrt to immediately handle Tab keystrokes.
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

                # Enter (\r or \n)
                if ch in ('\r', '\n'):
                    print()
                    return "".join(buffer)

                # Ctrl+C
                elif ch == '\x03':
                    print()
                    raise KeyboardInterrupt

                # Tab (\t) -> autocomplete first suggestion or cycle matches
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

                # Backspace (\x08 or \x7f)
                elif ch in ('\x08', '\x7f'):
                    last_was_tab = False
                    if buffer:
                        buffer.pop()
                        print('\b \b', end='', flush=True)
                    continue

                # Special keys (arrows, F-keys)
                elif ch in ('\x00', '\xe0'):
                    msvcrt.getwch()
                    continue

                # Normal character
                else:
                    last_was_tab = False
                    buffer.append(ch)
                    print(ch, end='', flush=True)
    except Exception:
        pass

    # Fallback to standard input
    setup_readline_completion(suggestions)
    try:
        return input(prompt_text)
    except (KeyboardInterrupt, EOFError):
        raise

def interactive_file_picker(start_dir: str = ".") -> str:
    """
    Interactive color terminal file browser.
    Color scheme:
      - Yellow: Current path header
      - Blue: Directories and [..]
      - White: Files (with gray size indicators)
      - Tab: Instant autocomplete of the first suggested file
    
    Returns: selected_path (str) or None if cancelled.
    """
    current_dir = os.path.abspath(start_dir)

    print("\n" + f"{Colors.CYAN}{'=' * 64}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD} === FILE SELECTION ASSISTANT ==={Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 64}{Colors.RESET}")
    print(f" {Colors.GRAY}Tip: Press {Colors.WHITE}[Tab]{Colors.GRAY} to autocomplete the first suggested file.{Colors.RESET}")
    print(f"      {Colors.GRAY}Enter item number, type {Colors.WHITE}'search <query>'{Colors.GRAY}, or {Colors.WHITE}'q'{Colors.GRAY} to cancel.{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * 64}{Colors.RESET}")

    while True:
        try:
            entries = os.listdir(current_dir)
        except Exception as e:
            print(f"{Colors.RED}[ERROR] Could not load directory '{current_dir}': {e}{Colors.RESET}")
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
        
        # 1. Yellow Path Header
        print(f"\n{Colors.YELLOW}{Colors.BOLD}📂 Path: {current_dir}{Colors.RESET}")
        print(f"{Colors.YELLOW}{'-' * 64}{Colors.RESET}")
        
        idx = 1
        parent_dir = os.path.dirname(current_dir)
        has_parent = parent_dir and parent_dir != current_dir

        # 2. Blue Directories
        if has_parent:
            print(f"  {Colors.BLUE_BOLD}[..] [UP] .. (Go to parent directory){Colors.RESET}")

        for d in dirs:
            print(f"  {Colors.BLUE_BOLD}[{idx:>2}] [DIR]  {d}/{Colors.RESET}")
            items_list.append(('dir', os.path.join(current_dir, d), d))
            idx += 1

        # 3. White Files
        for f in media_files:
            f_path = os.path.join(current_dir, f)
            size_str = get_file_size_str(f_path)
            size_display = f" {Colors.GRAY}({size_str}){Colors.RESET}" if size_str else ""
            print(f"  {Colors.WHITE}[{idx:>2}] [CLIP] {f}{Colors.RESET}{size_display}")
            items_list.append(('file', f_path, f))
            idx += 1

        # Other files (only if no media files found)
        if len(media_files) == 0 and other_files:
            for f in other_files[:15]:
                f_path = os.path.join(current_dir, f)
                print(f"  {Colors.WHITE}[{idx:>2}] [FILE] {f}{Colors.RESET}")
                items_list.append(('file', f_path, f))
                idx += 1

        if not dirs and not media_files and not other_files:
            print(f"  {Colors.GRAY}(This directory is empty){Colors.RESET}")

        # Prepare Tab suggestions (media files first, then directories)
        tab_candidates = []
        for f in media_files:
            tab_candidates.append(f)
        for d in dirs:
            tab_candidates.append(d)
        for i in range(1, len(items_list) + 1):
            tab_candidates.append(str(i))

        print(f"{Colors.YELLOW}{'-' * 64}{Colors.RESET}")
        try:
            prompt_str = f"Select [{Colors.CYAN}Tab{Colors.RESET}=first file / number / path / 'search' / 'q']: "
            choice = custom_tab_input(prompt_str, tab_candidates).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.GRAY}[Selection cancelled]{Colors.RESET}")
            return None

        if not choice:
            continue

        choice_lower = choice.lower()

        # Cancel
        if choice_lower in ['q', 'quit', 'exit', 'cancel']:
            print(f"{Colors.GRAY}[File selection cancelled]{Colors.RESET}")
            return None

        # Parent directory
        if choice == '..':
            if has_parent:
                current_dir = parent_dir
            else:
                print(f"{Colors.GRAY}[INFO] Already in root directory.{Colors.RESET}")
            continue

        # Search
        if choice_lower.startswith('search ') or choice_lower.startswith('find ') or choice_lower.startswith('f '):
            query = choice.split(' ', 1)[1].strip()
            print(f"\n{Colors.CYAN}[SEARCH] Searching for '{query}' in current folder and subfolders...{Colors.RESET}")
            search_results = search_media_files(current_dir, query)
            
            if not search_results:
                print(f"{Colors.YELLOW}[INFO] No media files matching '{query}' found.{Colors.RESET}")
                continue
                
            print(f"{Colors.GREEN}Found {len(search_results)} result(s):{Colors.RESET}")
            for s_idx, (rel_p, full_p, _) in enumerate(search_results, start=1):
                size_str = get_file_size_str(full_p)
                print(f"  {Colors.WHITE}[{s_idx:>2}] [CLIP] {rel_p}{Colors.RESET} {Colors.GRAY}({size_str}){Colors.RESET}")
                
            print(f"  {Colors.GRAY}[0] Back to directory browser{Colors.RESET}")
            try:
                s_choice = custom_tab_input(f"Select file number [1-{len(search_results)}]: ", [str(i) for i in range(1, len(search_results) + 1)]).strip()
                if s_choice.isdigit():
                    s_num = int(s_choice)
                    if 1 <= s_num <= len(search_results):
                        return search_results[s_num - 1][1]
            except (KeyboardInterrupt, EOFError):
                pass
            continue

        # Number selection
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
                print(f"{Colors.RED}[ERROR] Invalid option number '{choice}'.{Colors.RESET}")
                continue

        # Direct path / filename input
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
            print(f"{Colors.YELLOW}[WARNING] Path '{clean_input}' was not found on disk.{Colors.RESET}")
            try:
                ans = input("Do you still want to use this path? (y/n): ").strip().lower()
                if ans == 'y':
                    return clean_input
            except (KeyboardInterrupt, EOFError):
                return None

def handle_add(editor, args: list) -> bool:
    """
    Main handler function for the 'add' command.
    Accepts path only or opens the interactive file picker with Tab completion.
    Validates file media format.
    
    After selection, probes exact video duration and displays clip info.
    """
    file_path = None
    if args:
        file_path = " ".join(args).strip('\'"')

    # Launch interactive picker if no path was provided
    if not file_path:
        file_path = interactive_file_picker()
        if not file_path:
            return False

    file_path = file_path.strip('\'"')
    
    # 1. Existence check
    if not os.path.exists(file_path):
        norm_path = os.path.normpath(file_path)
        if not os.path.exists(norm_path):
            print(f"\n{Colors.YELLOW}[WARNING] File '{file_path}' was not found on disk!{Colors.RESET}")
            print("1. Open file picker assistant")
            print("2. Use the specified path anyway")
            print("3. Cancel")
            try:
                opt = input("Select option [1/2/3] (default 1): ").strip()
            except (KeyboardInterrupt, EOFError):
                return False
                
            if opt in ['1', '']:
                file_path = interactive_file_picker()
                if not file_path:
                    return False
            elif opt == '2':
                pass
            else:
                print(f"{Colors.GRAY}[Command 'add' cancelled]{Colors.RESET}")
                return False

    # 2. Guard against non-video / non-media formats
    is_valid, validation_reason = is_valid_media_file(file_path)
    if not is_valid:
        print(f"\n{Colors.RED}[WARNING] File '{file_path}' is not a supported media format!{Colors.RESET}")
        print(f"{Colors.GRAY}           Reason: {validation_reason}{Colors.RESET}")
        try:
            ans = input("Do you still want to add this file to the project? (y/n) [n]: ").strip().lower()
            if ans != 'y':
                print(f"{Colors.GRAY}[Command 'add' cancelled]{Colors.RESET}\n")
                return False
        except (KeyboardInterrupt, EOFError):
            return False

    # 3. Detect video duration
    print(f"{Colors.GRAY}[INFO] Detecting video duration...{Colors.RESET}")
    duration = get_video_duration(file_path)
    default_out = duration if duration != "Unknown" else None

    # Set current clip in editor
    editor.current_clip = {
        "path": file_path,
        "in": "00:00:00:00",
        "out": default_out,
        "duration": duration
    }
    
    clip_display = format_clip_name(file_path, max_len=12)
    
    # Information banner
    print()
    print(f"{Colors.GREEN}{'=' * 64}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD} [CLIP] Selected clip: {os.path.basename(file_path)}{Colors.RESET}")
    print(f"        {Colors.WHITE}Path:     {file_path}{Colors.RESET}")
    print(f"        {Colors.YELLOW}{Colors.BOLD}Duration: {duration}{Colors.RESET} {Colors.GRAY}(hh:mm:ss:centiseconds){Colors.RESET}")
    print(f"{Colors.GREEN}{'-' * 64}{Colors.RESET}")
    print(f" {Colors.CYAN}Clip editing commands:{Colors.RESET}")
    print(f"   {Colors.WHITE}start <time>{Colors.RESET} - Set start time (default: 00:00:00:00)")
    print(f"   {Colors.WHITE}stop <time>{Colors.RESET}  - Set end time   (currently: {default_out or 'entire video'})")
    print(f"   {Colors.WHITE}end{Colors.RESET}         - Save clip to timeline and return to menu")
    print(f"   {Colors.WHITE}help{Colors.RESET}        - Show help")
    print(f"{Colors.GREEN}{'=' * 64}{Colors.RESET}")
    print()
    return True

def handle_clip_start(clip: dict, args: list) -> bool:
    """
    Handle 'start' command in clip mode with try-except and chronological validation.
    Prevents start time >= stop time.
    """
    try:
        if not args:
            print(f"\n{Colors.RED}[ERROR] You must specify a start time. Example: start 00:01:30:00{Colors.RESET}\n")
            return False
            
        time_arg = args[0]
        if not is_time_format(time_arg):
            print(f"\n{Colors.RED}[ERROR] Invalid time format '{time_arg}'. Use format hh:mm:ss:centiseconds (e.g. 00:01:20:00).{Colors.RESET}\n")
            return False
            
        new_in_norm = normalize_time(time_arg)
        new_in_sec = time_to_seconds(new_in_norm)
        
        # Check against existing stop time
        current_out = clip.get('out')
        if current_out and current_out != "Unknown" and is_time_format(current_out):
            out_sec = time_to_seconds(current_out)
            if new_in_sec >= out_sec:
                print(f"\n{Colors.RED}[ERROR] Start time ({new_in_norm}) cannot be greater than or equal to end time ({current_out})!{Colors.RESET}")
                print(f"{Colors.GRAY}        (The clip would end before or at the same time it starts){Colors.RESET}\n")
                return False
                
        # Check against total video duration
        duration = clip.get('duration')
        if duration and duration != "Unknown" and is_time_format(duration):
            dur_sec = time_to_seconds(duration)
            if new_in_sec > dur_sec:
                print(f"\n{Colors.YELLOW}[WARNING] Specified start time ({new_in_norm}) exceeds total video duration ({duration})!{Colors.RESET}")
                try:
                    ans = input("Do you still want to set this time? (y/n): ").strip().lower()
                    if ans != 'y':
                        print(f"{Colors.GRAY}[Command 'start' cancelled]{Colors.RESET}\n")
                        return False
                except (KeyboardInterrupt, EOFError):
                    return False

        clip['in'] = new_in_norm
        print()
        print(f"{Colors.GREEN}[OK] Clip start set to: {new_in_norm}{Colors.RESET}")
        print(f"     Current cut: {Colors.WHITE}{new_in_norm} -> {clip.get('out') or 'end of video'}{Colors.RESET}")
        print()
        return True
    except Exception as e:
        print(f"\n{Colors.RED}[ERROR setting clip start]: {e}{Colors.RESET}\n")
        return False

def handle_clip_stop(clip: dict, args: list) -> bool:
    """
    Handle 'stop' / 'cutout' command in clip mode with try-except and chronological validation.
    Prevents stop time <= start time.
    """
    try:
        if not args:
            print(f"\n{Colors.RED}[ERROR] You must specify an end time. Example: stop 00:05:00:00{Colors.RESET}\n")
            return False
            
        time_arg = args[0]
        if not is_time_format(time_arg):
            print(f"\n{Colors.RED}[ERROR] Invalid time format '{time_arg}'. Use format hh:mm:ss:centiseconds (e.g. 00:05:00:00).{Colors.RESET}\n")
            return False
            
        new_out_norm = normalize_time(time_arg)
        new_out_sec = time_to_seconds(new_out_norm)
        
        # Check against start time (in)
        current_in = clip.get('in', '00:00:00:00')
        if current_in and is_time_format(current_in):
            in_sec = time_to_seconds(current_in)
            if new_out_sec <= in_sec:
                print(f"\n{Colors.RED}[ERROR] End time ({new_out_norm}) cannot be less than or equal to start time ({current_in})!{Colors.RESET}")
                print(f"{Colors.GRAY}        (The clip would end before or at the same time it starts){Colors.RESET}\n")
                return False
                
        # Check against total video duration
        duration = clip.get('duration')
        if duration and duration != "Unknown" and is_time_format(duration):
            dur_sec = time_to_seconds(duration)
            if new_out_sec > dur_sec:
                print(f"\n{Colors.YELLOW}[WARNING] Specified end time ({new_out_norm}) exceeds total video duration ({duration})!{Colors.RESET}")
                try:
                    ans = input("Do you still want to set this time? (y/n): ").strip().lower()
                    if ans != 'y':
                        print(f"{Colors.GRAY}[Command 'stop' cancelled]{Colors.RESET}\n")
                        return False
                except (KeyboardInterrupt, EOFError):
                    return False

        clip['out'] = new_out_norm
        print()
        print(f"{Colors.GREEN}[OK] Clip end set to:   {new_out_norm}{Colors.RESET}")
        print(f"     Current cut: {Colors.WHITE}{clip.get('in', '00:00:00:00')} -> {new_out_norm}{Colors.RESET}")
        print()
        return True
    except Exception as e:
        print(f"\n{Colors.RED}[ERROR setting clip end]: {e}{Colors.RESET}\n")
        return False
