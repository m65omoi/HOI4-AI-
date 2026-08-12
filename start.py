# -*- coding: utf-8 -*-
"""
HOI4 AI Translator Launcher
Checks dependencies, auto-starts Ollama, and launches the GUI
"""
import sys
import os
import subprocess
import time
import socket

# Windows process creation flags
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def check_python_version():
    if sys.version_info < (3, 8):
        print("=" * 50)
        print("ERROR: Python 3.8 or higher is required!")
        print(f"Current version: {sys.version}")
        print("Download: https://www.python.org/downloads/")
        print("=" * 50)
        input("Press Enter to exit...")
        sys.exit(1)


def install_requirements():
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    flag_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements_installed.flag")
    
    if os.path.exists(flag_file):
        return True
    
    print("Installing dependencies...")
    print("=" * 50)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file],
            capture_output=False
        )
        if result.returncode == 0:
            with open(flag_file, 'w') as f:
                f.write("installed")
            print("=" * 50)
            print("Dependencies installed successfully!")
            return True
        else:
            print("ERROR: Failed to install dependencies")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def is_ollama_running(host="localhost", port=11434, timeout=2):
    """Check if Ollama server is already running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def find_ollama_executable():
    """Find Ollama executable path."""
    # 1. Check PATH first
    try:
        result = subprocess.run(
            ["where", "ollama"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')[0].strip()
    except Exception:
        pass
    
    # 2. Check default installation paths
    possible_paths = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Ollama", "ollama.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Ollama", "ollama.exe"),
        os.path.expanduser("~\\AppData\\Local\\Programs\\Ollama\\ollama.exe"),
    ]
    
    for path in possible_paths:
        if os.path.isfile(path):
            return path
    
    return None


def wait_for_ollama(host="localhost", port=11434, timeout=30):
    """Wait for Ollama to become ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_ollama_running(host, port):
            # Also check if API responds
            try:
                import urllib.request
                req = urllib.request.Request(f"http://{host}:{port}/api/tags")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
        time.sleep(1)
        print(".", end="", flush=True)
    return False


def start_ollama():
    """Start Ollama if not running. Returns True if Ollama is ready."""
    print("[CHECK] Checking Ollama service...")
    
    if is_ollama_running():
        print("[OK] Ollama is already running")
        return True
    
    print("[INFO] Ollama not detected, trying to start...")
    
    # Find ollama executable
    ollama_path = find_ollama_executable()
    
    if not ollama_path:
        print()
        print("=" * 50)
        print("[WARNING] Ollama not found!")
        print()
        print("Please install Ollama first:")
        print("  Download: https://ollama.com/download")
        print()
        print("After installing, pull the translation model:")
        print("  ollama pull qwen2.5:7b-instruct")
        print("=" * 50)
        print()
        choice = input("Start anyway? (y/n): ").strip().lower()
        return choice in ('y', 'yes', '')
    
    print(f"[INFO] Found Ollama at: {ollama_path}")
    print("[INFO] Starting Ollama...", end="", flush=True)
    
    try:
        # Start Ollama serve in background
        # On Windows, ollama app starts the server automatically
        # First try starting the app, if that fails try 'ollama serve'
        ollama_dir = os.path.dirname(ollama_path)
        
        # Try launching ollama app first (hidden window in background)
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS
        
        subprocess.Popen(
            [ollama_path],
            cwd=ollama_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        
        # Wait for it to start
        if wait_for_ollama(timeout=20):
            print()
            print("[OK] Ollama started successfully")
            return True
        else:
            print()
            print("[WARNING] Ollama started but may not be ready yet")
            return True
            
    except Exception as e:
        print()
        print(f"[ERROR] Failed to start Ollama: {e}")
        print("Please start Ollama manually before using the translator.")
        return True  # Continue anyway, GUI will show connection status


def check_default_model():
    """Check if recommended model is available."""
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                models = [m.get("name", "") for m in data.get("models", [])]
                
                # Check for any supported translation model
                supported_families = ["qwen2.5", "deepseek-r1", "deepseek-v2", "deepseek-llm", 
                                     "llama3.1", "mistral", "glm4"]
                has_model = any(any(family in m.lower() for family in supported_families) for m in models)
                
                if not has_model:
                    print()
                    print("[INFO] No supported translation model found!")
                    print("       Run one of these commands to download a model:")
                    print("       ollama pull qwen2.5:7b-instruct     (Recommended - best Chinese)")
                    print("       ollama pull deepseek-r1:7b         (Good quality, reasoning model)")
                    print("       ollama pull deepseek-r1:14b        (Higher quality, needs more VRAM)")
                    print()
                    print(f"       Available models: {', '.join(models[:5]) if models else 'none'}")
                    print()
                else:
                    print(f"[OK] Model(s) available: {', '.join(models[:3])}")
    except Exception:
        pass


def main():
    print("=" * 50)
    print("  Hearts of Iron IV AI Translator")
    print("  HOI4 AI Localization Assistant")
    print("=" * 50)
    print()
    
    # Check Python version
    check_python_version()
    print(f"[OK] Python {sys.version.split()[0]}")
    
    # Install dependencies
    if not install_requirements():
        print("\nFailed to install dependencies. Please run manually:")
        print(f"  pip install -r requirements.txt")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Auto-start Ollama
    start_ollama()
    time.sleep(1)
    check_default_model()
    print()
    
    # Add src to path and launch GUI
    app_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(app_dir, 'src'))
    
    try:
        from src.gui import launch_gui
        print("[OK] Launching GUI...")
        print()
        launch_gui()
    except ImportError as e:
        print(f"ERROR: Cannot import modules: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
