import os
import sys
import subprocess
import json
from add_clip import handle_add, format_clip_name, time_to_ffmpeg, normalize_time

class IHP_Editor:
    def __init__(self):
        self.project_file = "project.ihp"
        self.timeline = []
        self.current_clip = None
        self.unsaved_changes = False

        self.commands_main = {
            "add": "Přidá klip do projektu. Použití: add [cesta] (nebo jen add pro asistenta s [Tab]).",
            "back": "Smaže poslední klip z časové osy.",
            "ls, rm, mv": "Propouští tyto systémové příkazy přímo do terminálu.",
            "write / wr": "Uloží aktuální projekt na disk.",
            "render": "Vyrenderuje projekt přes FFmpeg. Použití: render <vystup.mp4>",
            "help": "Zobrazí nápovědu. Použití: help [příkaz]",
            "exit": "Ukončí IHP (zeptá se na uložení, pokud jsou změny)."
        }

        self.commands_clip = {
            "start": "Nastaví počáteční čas klipu. Použití: start <čas (hh:mm:ss:setiny)>",
            "stop": "Nastaví koncový čas klipu. Použití: stop <čas (hh:mm:ss:setiny)>",
            "cutout": "Alias pro příkaz stop.",
            "info": "Zobrazí podrobné informace o klipu, délce a nastaveném střihu.",
            "end": "Ukončí editaci klipu, uloží ho na časovou osu a vrátí se do hlavního menu.",
            "help": "Zobrazí nápovědu. Použití: help [příkaz]"
        }

    def cmd_help(self, args, context_commands):
        if not args:
            print("\n=== Nápověda IHP (I Hate Premiere) ===")
            for cmd, desc in context_commands.items():
                print(f"  {cmd:<10} - {desc}")
            print("======================================\n")
        else:
            cmd = args[0]
            if cmd in context_commands:
                print(f"{cmd}: {context_commands[cmd]}")
            else:
                print(f"Neznámý příkaz '{cmd}'.")

    def cmd_write(self):
        try:
            with open(self.project_file, 'w') as f:
                json.dump(self.timeline, f, indent=4)
            self.unsaved_changes = False
            print(f"[OK] Projekt uložen do {self.project_file}")
        except Exception as e:
            print(f"[CHYBA] Nelze uložit projekt: {e}")

    def cmd_render(self, args):
        if not self.timeline:
            print("[CHYBA] Časová osa je prázdná, není co renderovat.")
            return
        
        output_file = args[0] if args else "hotovo.mp4"
        total_clips = len(self.timeline)
        print(f"\n[RENDER] Začínám zpracovávat {total_clips} klipů...\n")
        
        temp_files = []
        
        # FÁZE 1: Zpracování jednotlivých řádků (klipů)
        for i, clip in enumerate(self.timeline):
            temp_out = f"ihp_temp_{i}.mp4"
            temp_files.append(temp_out)
            
            # Sestavení příkazu pro oříznutí konkrétního klipu
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", clip["path"]]
            clip_in = time_to_ffmpeg(clip.get("in", "00:00:00:00"))
            if clip_in != "00:00:00":
                ffmpeg_cmd.extend(["-ss", clip_in])
            if clip.get("out"):
                clip_out = time_to_ffmpeg(clip["out"])
                ffmpeg_cmd.extend(["-to", clip_out])
                
            # Přidáme parametry pro libx264 a potlačíme výstup (-loglevel error)
            ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "fast", "-loglevel", "error", temp_out])
            
            try:
                subprocess.run(ffmpeg_cmd, check=True)
            except subprocess.CalledProcessError as e:
                print(f"\n[CHYBA] Selhalo zpracování klipu {clip['path']}. Přeskočeno.")
                continue
            
            # Vykreslení ASCII progressbaru přepisováním řádku (\r)
            percent = int(((i + 1) / total_clips) * 100)
            bar = "#" * (percent // 5) + "-" * (20 - (percent // 5))
            print(f"\r[RENDER] Progress: [{bar}] {percent}% (Hotovo {i+1}/{total_clips} klipů)", end="", flush=True)
            
        print("\n\n[RENDER] Spojuji klipy do finálního souboru...")
        
        # FÁZE 2: Bleskové spojení (concat demuxer) beze ztráty kvality (-c copy)
        concat_file = "ihp_concat_list.txt"
        try:
            with open(concat_file, 'w') as f:
                for tmp in temp_files:
                    if os.path.exists(tmp):
                        f.write(f"file '{os.path.abspath(tmp)}'\n")
                    
            concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-loglevel", "error", output_file]
            subprocess.run(concat_cmd, check=True)
            
            print(f"[RENDER] HOTOVO! Video uloženo jako: {output_file} 🎉")
        except Exception as e:
            print(f"[CHYBA] Selhalo spojování klipů: {e}")
        finally:
            # Úklid dočasných souborů
            if os.path.exists(concat_file):
                os.remove(concat_file)
            for tmp in temp_files:
                if os.path.exists(tmp):
                    os.remove(tmp)

    def run(self):
        print("Vítejte v IHP (I Hate Premiere) - The CLI Video Editor")
        print("Zadejte 'help' pro seznam příkazů.")

        while True:
            # Sestavení promptu - název klipu zkrácen na max. 12 znaků
            if self.current_clip:
                short_name = format_clip_name(self.current_clip['path'], max_len=12)
                prompt = f"ihp ({short_name}) > "
            else:
                prompt = "ihp > "

            try:
                line = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nPro ukončení použijte příkaz 'exit'.")
                continue

            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            # 1. REŽIM UVNITŘ KLIPU
            if self.current_clip:
                if cmd == "end":
                    self.timeline.append(self.current_clip)
                    self.current_clip = None
                    self.unsaved_changes = True
                    print("\n[OK] Klip byl úspěšně přidán na časovou osu.\n")

                elif cmd == "start":
                    if not args:
                        print("\n[CHYBA] Musíte zadat počáteční čas. Příklad: start 00:01:30:00\n")
                    else:
                        norm_in = normalize_time(args[0])
                        self.current_clip['in'] = norm_in
                        print()
                        print(f"[OK] Začátek klipu nastaven na: {norm_in}")
                        print(f"     Aktuální střih: {norm_in} -> {self.current_clip.get('out') or 'konec videa'}")
                        print()

                elif cmd in ["stop", "cutout", "cut"]:
                    if not args:
                        print("\n[CHYBA] Musíte zadat koncový čas. Příklad: stop 00:05:00:00\n")
                    else:
                        norm_out = normalize_time(args[0])
                        self.current_clip['out'] = norm_out
                        print()
                        print(f"[OK] Konec klipu nastaven na:   {norm_out}")
                        print(f"     Aktuální střih: {self.current_clip.get('in', '00:00:00:00')} -> {norm_out}")
                        print()

                elif cmd == "info":
                    print()
                    print("-" * 50)
                    print(f"  Soubor:  {self.current_clip['path']}")
                    print(f"  Délka:   {self.current_clip.get('duration', 'Neznámá')}")
                    print(f"  Začátek: {self.current_clip.get('in', '00:00:00:00')}")
                    print(f"  Konec:   {self.current_clip.get('out') or 'Konec videa'}")
                    print("-" * 50)
                    print()

                elif cmd == "help":
                    self.cmd_help(args, self.commands_clip)
                else:
                    print(f"\nNeznámý příkaz v režimu klipu. Zadejte 'start <čas>', 'stop <čas>', 'end' nebo 'help'.\n")
                continue

            # 2. REŽIM HLAVNÍHO MENU
            if cmd == "add":
                handle_add(self, args)
            
            elif cmd == "back":
                if self.timeline:
                    removed = self.timeline.pop()
                    self.unsaved_changes = True
                    print(f"[OK] Poslední klip ({removed['path']}) byl smazán z časové osy.")
                else:
                    print("[INFO] Časová osa je prázdná, není co mazat.")

            # Propouštění příkazů pro správu souborů rovnou do systému
            elif cmd in ["ls", "rm", "mv"]:
                try:
                    subprocess.run([cmd] + args)
                except Exception as e:
                    print(f"[CHYBA] Nelze spustit příkaz '{cmd}': {e}")

            elif cmd in ["write", "wr"]:
                self.cmd_write()

            elif cmd == "render":
                self.cmd_render(args)

            elif cmd == "help":
                self.cmd_help(args, self.commands_main)

            elif cmd == "exit":
                if self.unsaved_changes:
                    ans = input("Máte neuložené změny! Chcete před odchodem uložit projekt? (y/n/c): ").lower()
                    if ans == 'y':
                        self.cmd_write()
                        sys.exit(0)
                    elif ans == 'n':
                        sys.exit(0)
                else:
                    sys.exit(0)
            else:
                print(f"Neznámý příkaz '{cmd}'. Zadejte 'help' pro nápovědu.")

if __name__ == "__main__":
    # Aby fungovalo překreslování progressbaru (\r), je dobré zajistit správné kódování
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
    app = IHP_Editor()
    app.run()


