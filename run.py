import sys
import argparse
import subprocess
import os

def main():
    parser = argparse.ArgumentParser(description="Book Finder - One-stop runner")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "setup", "search", "details", "sync", "guide", "stats", "index", "recommend"],
                        help="Command to run (default: serve)")
    parser.add_argument("--stage", choices=["all", "ingest", "transform", "store"], default="all", help="Stage for setup")
    parser.add_argument("--limit", type=int, help="Limit for setup")
    
    # Capture all other args
    args, unknown = parser.parse_known_args()
    
    if args.command == "recommend":
        cmd = ["python", "-m", "streamlit", "run", "app/ui.py"]
    else:
        cmd = ["python", "-m", "app.cli", args.command]
    
    if args.command == "setup":
        if args.stage: cmd.extend(["--stage", args.stage])
        if args.limit: cmd.extend(["--limit", str(args.limit)])
    elif args.command in ["search", "details", "sync"]:
        # Pass through unknown args for these commands
        cmd.extend(unknown)
        
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
