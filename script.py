import os
import io
import sys
import json
import requests
import winshell
import tempfile
import shutil
import time
import concurrent.futures
import tkinter as tk
from tkinter import filedialog
from zipfile import ZipFile

SHORTCUT_NAME = "Lethal Company (M4CKD0GE Repack).lnk"
GITHUB_REPO   = "https://api.github.com/repos/Duckey86/customCosmetics/contents/"
BEPINEX_PACK_URL = "https://github.com/Duckey86/customCosmetics/raw/refs/heads/main/BepInEx-BepInExPack-5.4.2305.zip"

HSR_RELEASE_URL = "https://github.com/Duckey86/customCosmetics/releases/download/Release1/inki-HSRSuits-3.1.0.zip"
WESLEY_INTERIOR_URL = "https://github.com/Duckey86/customCosmetics/releases/download/Release2/21Magic_Wesley-Wesleys_Weathers-1.2.11.zip"
WESLEY_MOONS_URL = "https://github.com/Duckey86/customCosmetics/releases/download/Release3/Magic_Wesley-Wesleys_Moons-6.9.14.zip"

STATE_FILE = "mod_installer_state.json"

# --- Performance tuning ---
PARALLEL_THREADS = 8               # Number of parallel connections for large files (>100 MB)
PARALLEL_THRESHOLD_MB = 100        # Use parallel download if file larger than this (MB)
CHUNK_SIZE_SINGLE = 16 * 1024 * 1024    # 1 MB for single‑thread streaming
CHUNK_SIZE_PARALLEL = 16 * 1024 * 1024  # 1 MB per part thread


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def load_install_state(game_folder):
    state_path = os.path.join(game_folder, STATE_FILE)
    if os.path.exists(state_path):
        try:
            with open(state_path, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_install_state(game_folder, state):
    state_path = os.path.join(game_folder, STATE_FILE)
    try:
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[WARN] Could not save state: {e}")


def get_game_folder_from_shortcut():
    possible_dirs = [
        os.path.join(os.environ["PUBLIC"], "Desktop"),
        os.path.join(os.environ["USERPROFILE"], "Desktop"),
        os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ["PROGRAMDATA"], "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    for base in possible_dirs:
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.lower() == SHORTCUT_NAME.lower():
                    full = os.path.join(root, f)
                    try:
                        with winshell.shortcut(full) as link:
                            return os.path.dirname(link.path)
                    except Exception:
                        continue
    print("[INFO] Could not auto‑find shortcut. Please select it manually.")
    root = tk.Tk()
    root.withdraw()
    shortcut_path = filedialog.askopenfilename(
        title="Select the Lethal Company shortcut",
        filetypes=[("Shortcuts", "*.lnk")]
    )
    root.destroy()
    if shortcut_path and os.path.exists(shortcut_path):
        try:
            with winshell.shortcut(shortcut_path) as link:
                return os.path.dirname(link.path)
        except Exception:
            return None
    return None


def validate_bepinex(game_folder):
    missing = []
    if not os.path.isdir(os.path.join(game_folder, "BepInEx")):
        missing.append("BepInEx/")
    if not os.path.exists(os.path.join(game_folder, "doorstop_config.ini")):
        missing.append("doorstop_config.ini")
    if not os.path.exists(os.path.join(game_folder, "winhttp.dll")):
        missing.append("winhttp.dll")
    return missing


def safe_makedirs(path):
    if os.path.isfile(path):
        print(f"[WARN] Cannot create directory: {path} (file exists). Skipping.")
        return False
    os.makedirs(path, exist_ok=True)
    return True


def install_bepinex(game_folder):
    print("[SETUP] BepInEx incomplete – downloading & installing missing pieces...")
    r = requests.get(BEPINEX_PACK_URL)
    r.raise_for_status()
    with ZipFile(io.BytesIO(r.content)) as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            parts = member.split("/", 1)
            if len(parts) != 2:
                continue
            _, inner = parts
            inner = os.path.normpath(inner).replace("\\", "/")
            if inner.startswith(".."):
                continue
            target = os.path.join(game_folder, inner)
            if os.path.exists(target):
                print(f"  [SKIP] already exists: {inner}")
                continue
            if not safe_makedirs(os.path.dirname(target)):
                continue
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    print("[OK] BepInEx is now complete.\n")


def compute_target_path(zip_member_path, game_folder):
    norm = os.path.normpath(zip_member_path).replace("\\", "/")
    parts = [p for p in norm.split("/") if p and p != "."]
    if not parts:
        return None
    bepinex_idx = None
    for i, p in enumerate(parts):
        if p.lower() == "bepinex":
            bepinex_idx = i
            break
    if bepinex_idx is not None:
        rel_parts = parts[bepinex_idx + 1:]
        if not rel_parts:
            return None
        target = os.path.join(game_folder, "BepInEx", *rel_parts)
        return target
    else:
        first = parts[0].lower()
        if first in ("plugins", "config", "patchers", "core"):
            target = os.path.join(game_folder, "BepInEx", *parts)
            return target
        else:
            target = os.path.join(game_folder, "BepInEx", "plugins", *parts)
            return target


def download_single_thread(session, url, dest_path, timeout=30):
    """Single‑thread streaming download with 1 MB chunks."""
    with session.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get('content-length', 0))
        downloaded = 0
        bar_width = 50
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE_SINGLE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = downloaded / total * 100
                        filled = int(bar_width * downloaded / total)
                        bar = '█' * filled + '░' * (bar_width - filled)
                        dl_mb = downloaded / (1024**2)
                        total_mb = total / (1024**2)
                        sys.stdout.write(f'\r> [{bar}] {percent:.1f}% ({dl_mb:.1f}/{total_mb:.1f} MB)')
                    else:
                        dl_mb = downloaded / (1024**2)
                        sys.stdout.write(f'\r> [DOWNLOAD] {dl_mb:.1f} MB ...')
                    sys.stdout.flush()
        print()
    return True


def download_parallel(session, url, dest_path, num_threads=PARALLEL_THREADS, timeout=30):
    """Parallel chunked download using HTTP Range."""
    # Get file size and check range support
    resp_head = session.head(url, timeout=timeout)
    resp_head.raise_for_status()
    total = int(resp_head.headers.get('content-length', 0))
    accept_ranges = resp_head.headers.get('accept-ranges', '').lower() == 'bytes'
    if not accept_ranges or total <= 0:
        print("> Server doesn't support parallel – using single thread.")
        return download_single_thread(session, url, dest_path, timeout)

    # Calculate parts
    part_size = total // num_threads
    ranges = []
    for i in range(num_threads):
        start = i * part_size
        end = (start + part_size - 1) if i < num_threads - 1 else total - 1
        ranges.append((start, end))

    temp_dir = os.path.dirname(dest_path)
    part_files = []

    def download_part(start, end, idx):
        part_path = os.path.join(temp_dir, f".part_{idx}_{os.path.basename(dest_path)}")
        headers = {'Range': f'bytes={start}-{end}'}
        try:
            with session.get(url, headers=headers, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                with open(part_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE_PARALLEL):
                        f.write(chunk)
            return part_path
        except Exception as e:
            print(f"\n  [ERROR] Part {idx+1} failed: {e}")
            return None

    print(f"> [PARALLEL] Downloading {total/(1024**2):.1f} MB using {num_threads} threads...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_idx = {executor.submit(download_part, start, end, i): i for i, (start, end) in enumerate(ranges)}
        for future in concurrent.futures.as_completed(future_to_idx):
            part_path = future.result()
            if part_path:
                part_files.append(part_path)
            else:
                print("> Parallel download failed – falling back to single thread.")
                for pf in part_files:
                    if os.path.exists(pf):
                        os.unlink(pf)
                return download_single_thread(session, url, dest_path, timeout)

    # Merge parts
    print("> [MERGE] Combining parts...")
    with open(dest_path, 'wb') as outfile:
        for part_path in sorted(part_files, key=lambda p: int(p.split('_part_')[1].split('_')[0])):
            with open(part_path, 'rb') as infile:
                shutil.copyfileobj(infile, outfile)
            os.unlink(part_path)
    return True


def download_with_retry(session, url, dest_path, max_retries=3, timeout=30):
    """Smart download: parallel for large files, else single."""
    for attempt in range(1, max_retries + 1):
        try:
            # Get file size via HEAD
            resp_head = session.head(url, timeout=timeout)
            resp_head.raise_for_status()
            total_bytes = int(resp_head.headers.get('content-length', 0))
            total_mb = total_bytes / (1024**2)

            if total_mb > PARALLEL_THRESHOLD_MB:
                success = download_parallel(session, url, dest_path, timeout=timeout)
            else:
                success = download_single_thread(session, url, dest_path, timeout=timeout)

            if success:
                return True
        except Exception as e:
            print(f"\n> [RETRY {attempt}/{max_retries}] Error: {e}")
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"> waiting {wait} seconds...")
                time.sleep(wait)
            else:
                print(f"> [ERROR] All retries failed for {url}")
                return False
    return False


def process_zip(session, url, game_folder, label="", state=None):
    if state and url in state:
        print(f"\n> [SKIP] {label + ': ' if label else ''}{url.split('/')[-1]} – already installed.")
        return

    print(f"\n> >>> {label + ': ' if label else ''}{url.split('/')[-1]}")
    print(f"> [FETCH] {url}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        tmp_path = tmp_file.name

    success = download_with_retry(session, url, tmp_path, max_retries=3, timeout=30)
    if not success:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        print(f"> [FAIL] Could not download {url.split('/')[-1]}")
        return

    print(f"> [UNPACK] extracting from temporary file...")
    try:
        with ZipFile(tmp_path, 'r') as zf:
            files_to_extract = []
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                target = compute_target_path(member, game_folder)
                if not target:
                    continue
                files_to_extract.append((member, target))

            if not files_to_extract:
                print("> [SKIP] No BepInEx files found in this ZIP.")
                return

            if all(os.path.exists(t) for _, t in files_to_extract):
                print(f"> [SKIP] All {len(files_to_extract)} files already present.")
                if state is not None:  # <-- add these 3 lines
                    state[url] = True
                    save_install_state(game_folder, state)
                return

            print(f"> [UNPACK] extracting new files (keeping existing ones)...")
            for member, target in files_to_extract:
                if os.path.exists(target):
                    print(f"  [KEEP] {os.path.relpath(target, game_folder)}")
                    continue
                if not safe_makedirs(os.path.dirname(target)):
                    continue
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                size_kb = os.path.getsize(target) / 1024
                print(f"  [WRITE] {os.path.relpath(target, game_folder)} ({size_kb:.1f} KB)")

        if state is not None:
            state[url] = True
            save_install_state(game_folder, state)

    except Exception as e:
        print(f"> [ERROR] Extraction failed: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print(f"> [DEPLOY] {url.split('/')[-1]} :: done ✔")


def load_banner():
    try:
        with open(resource_path("banner.txt"), "r", encoding="utf-8") as f:
            print(f.read())
    except FileNotFoundError:
        print("[WARN] banner not found")


def main():
    load_banner()

    print("[INIT] locating game installation...")
    game_folder = get_game_folder_from_shortcut()

    if not game_folder:
        print("[INFO] No shortcut selected – please enter the path manually.")
        game_folder = input('Path to Lethal Company folder (e.g., C:\\Games\\Lethal Company): ').strip('"')
        if not os.path.isdir(game_folder):
            print(f"[ERROR] '{game_folder}' does not exist.")
            input("\n[EXIT] Press Enter to close...")
            return
        print(f"[OK] using folder: {game_folder}")
    else:
        print(f"[OK] target located: {game_folder}")

    install_state = load_install_state(game_folder)

    missing = validate_bepinex(game_folder)
    if missing:
        print("[INFO] BepInEx is missing or incomplete:")
        for m in missing:
            print(" -", m)
        install_bepinex(game_folder)
    else:
        print("[OK] BepInEx present.\n")

    session = requests.Session()
    print("[NET] fetching mod list from GitHub repo...")
    try:
        contents = session.get(GITHUB_REPO).json()
    except Exception as e:
        print(f"[ERROR] Could not read repo: {e}")
        input("\n[EXIT] Press Enter to close...")
        return

    zip_urls = [
        f["download_url"] for f in contents
        if f["name"].endswith(".zip") and not f["name"].startswith("BepInEx-BepInExPack")
    ]

    more_suits_url = None
    others = []
    for url in zip_urls:
        if "More_Suits" in url:
            more_suits_url = url
        else:
            others.append(url)

    if not more_suits_url:
        print("[WARN] More Suits mod not found in repo – proceeding anyway.")
    else:
        process_zip(session, more_suits_url, game_folder, "More Suits (priority)", install_state)

    for url in others:
        process_zip(session, url, game_folder, "", install_state)

    print("\n--- Installing large HSR package ---")
    process_zip(session, HSR_RELEASE_URL, game_folder, "HSR Release", install_state)

    print("\n--- Installing Wesley's Interiors package ---")
    process_zip(session, WESLEY_INTERIOR_URL, game_folder, "Wesley's Interiors", install_state)

    print("\n--- Installing Wesley's Moons package ---")
    process_zip(session, WESLEY_MOONS_URL, game_folder, "Wesley's Moons", install_state)

    print("\n[ROOT] all mods deployed (nothing was overwritten).")
    input("\n[EXIT] Press Enter to close...")


if __name__ == "__main__":
    main()