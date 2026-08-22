import os
import sys
import subprocess
import json
from add_clip import (
    handle_add,
    format_clip_name,
    time_to_ffmpeg,
    normalize_time,
    handle_clip_start,
    handle_clip_stop
)

class IHP_Editor:
    def __init__(self):
        self.project_file = "project.ihp"
        self.timeline = []
        self.current_clip = None
        self.unsaved_changes = False

        self.commands_main = {
            "add": "Add a clip to the project. Usage: add [path] (or 'add' for interactive browser with [Tab]).",
            "back": "Remove the last clip from the timeline.",
            "ls, rm, mv": "Pass these system commands directly to the terminal.",
            "write / wr": "Save the current project to disk.",
            "render": "Render the project using FFmpeg. Usage: render <output.mp4>",
            "help": "Show help. Usage: help [command]",
            "exit": "Exit IHP (prompts to save if there are unsaved changes)."
        }

        self.commands_clip = {
            "start": "Set the starting time of the clip. Usage: start <time (hh:mm:ss:centiseconds)>",
            "stop": "Set the ending time of the clip. Usage: stop <time (hh:mm:ss:centiseconds)>",
            "cutout": "Alias for the 'stop' command.",
            "info": "Show details about the current clip, video duration, and cut range.",
            "end": "Finish editing the clip, save it to the timeline, and return to the main menu.",
            "help": "Show help. Usage: help [command]"
        }

    def cmd_help(self, args, context_commands):
        if not args:
            print("\n=== IHP Help (I Hate Premiere) ===")
            for cmd, desc in context_commands.items():
                print(f"  {cmd:<10} - {desc}")
            print("==================================\n")
        else:
            cmd = args[0]
            if cmd in context_commands:
                print(f"{cmd}: {context_commands[cmd]}")
            else:
                print(f"Unknown command '{cmd}'.")

    def cmd_write(self):
        try:
            with open(self.project_file, 'w') as f:
                json.dump(self.timeline, f, indent=4)
            self.unsaved_changes = False
            print(f"[OK] Project saved to {self.project_file}")
        except Exception as e:
            print(f"[ERROR] Could not save project: {e}")

    def cmd_render(self, args):
        if not self.timeline:
            print("[ERROR] Timeline is empty, nothing to render.")
            return
        
        output_file = args[0] if args else "output.mp4"
        total_clips = len(self.timeline)
        print(f"\n[RENDER] Processing {total_clips} clip(s)...\n")
        
        temp_files = []
        
        # PHASE 1: Process individual clips (trimming)
        for i, clip in enumerate(self.timeline):
            temp_out = f"ihp_temp_{i}.mp4"
            temp_files.append(temp_out)
            
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", clip["path"]]
            clip_in = time_to_ffmpeg(clip.get("in", "00:00:00:00"))
            if clip_in != "00:00:00":
                ffmpeg_cmd.extend(["-ss", clip_in])
            if clip.get("out"):
                clip_out = time_to_ffmpeg(clip["out"])
                ffmpeg_cmd.extend(["-to", clip_out])
                
            # Add encoding parameters and suppress verbose logs
            ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "fast", "-loglevel", "error", temp_out])
            
            try:
                subprocess.run(ffmpeg_cmd, check=True)
            except subprocess.CalledProcessError:
                print(f"\n[ERROR] Failed to process clip {clip['path']}. Skipped.")
                continue
            
            # Draw ASCII progress bar (\r)
            percent = int(((i + 1) / total_clips) * 100)
            bar = "#" * (percent // 5) + "-" * (20 - (percent // 5))
            print(f"\r[RENDER] Progress: [{bar}] {percent}% (Done {i+1}/{total_clips} clips)", end="", flush=True)
            
        valid_temp_files = [tmp for tmp in temp_files if os.path.exists(tmp) and os.path.getsize(tmp) > 0]
        if not valid_temp_files:
            print("\n\n[ERROR] None of the clips could be rendered (files not found or invalid format). Rendering aborted.")
            return

        print("\n\n[RENDER] Concatenating clips into final file...")
        
        # PHASE 2: Fast concatenation (concat demuxer) without quality loss (-c copy)
        concat_file = "ihp_concat_list.txt"
        try:
            with open(concat_file, 'w') as f:
                for tmp in valid_temp_files:
                    f.write(f"file '{os.path.abspath(tmp)}'\n")
                    
            concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-loglevel", "error", output_file]
            subprocess.run(concat_cmd, check=True)
            
            print(f"[RENDER] DONE! Video saved as: {output_file} 🎉")
        except Exception as e:
            print(f"[ERROR] Failed to concatenate clips: {e}")
        finally:
            # Cleanup temporary files
            if os.path.exists(concat_file):
                os.remove(concat_file)
            for tmp in temp_files:
                if os.path.exists(tmp):
                    os.remove(tmp)

    def run(self):
        print("Welcome to IHP (I Hate Premiere) - The CLI Video Editor")
        print("Type 'help' for a list of commands.")

        while True:
            # Build prompt - clip name truncated to max 12 characters
            if self.current_clip:
                short_name = format_clip_name(self.current_clip['path'], max_len=12)
                prompt = f"ihp ({short_name}) > "
            else:
                prompt = "ihp > "

            try:
                line = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nTo exit, use the 'exit' command.")
                continue

            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            # 1. INSIDE CLIP MODE
            if self.current_clip:
                if cmd == "end":
                    self.timeline.append(self.current_clip)
                    self.current_clip = None
                    self.unsaved_changes = True
                    print("\n[OK] Clip was successfully added to the timeline.\n")

                elif cmd == "start":
                    handle_clip_start(self.current_clip, args)

                elif cmd in ["stop", "cutout", "cut"]:
                    handle_clip_stop(self.current_clip, args)

                elif cmd == "info":
                    print()
                    print("-" * 50)
                    print(f"  File:     {self.current_clip['path']}")
                    print(f"  Duration: {self.current_clip.get('duration', 'Unknown')}")
                    print(f"  Start:    {self.current_clip.get('in', '00:00:00:00')}")
                    print(f"  End:      {self.current_clip.get('out') or 'End of video'}")
                    print("-" * 50)
                    print()

                elif cmd == "help":
                    self.cmd_help(args, self.commands_clip)
                else:
                    print(f"\nUnknown command in clip mode. Use 'start <time>', 'stop <time>', 'end', or 'help'.\n")
                continue

            # 2. MAIN MENU MODE
            if cmd == "add":
                handle_add(self, args)
            
            elif cmd == "back":
                if self.timeline:
                    removed = self.timeline.pop()
                    self.unsaved_changes = True
                    print(f"[OK] Last clip ({removed['path']}) was removed from the timeline.")
                else:
                    print("[INFO] Timeline is empty, nothing to delete.")

            # Pass file management commands directly to system
            elif cmd in ["ls", "rm", "mv"]:
                try:
                    subprocess.run([cmd] + args)
                except Exception as e:
                    print(f"[ERROR] Could not execute command '{cmd}': {e}")

            elif cmd in ["write", "wr"]:
                self.cmd_write()

            elif cmd == "render":
                self.cmd_render(args)

            elif cmd == "help":
                self.cmd_help(args, self.commands_main)

            elif cmd == "exit":
                if self.unsaved_changes:
                    ans = input("You have unsaved changes! Do you want to save the project before exiting? (y/n/c): ").lower()
                    if ans == 'y':
                        self.cmd_write()
                        sys.exit(0)
                    elif ans == 'n':
                        sys.exit(0)
                else:
                    sys.exit(0)
            else:
                print(f"Unknown command '{cmd}'. Type 'help' for help.")

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
    app = IHP_Editor()
    app.run()
