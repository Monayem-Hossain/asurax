#!/usr/bin/env python3
import os
import sys
import json
import time
import shutil
import glob
import re
import argparse
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

def ensure_packages():
    import importlib
    
    for lib, pkg in [("requests", "requests"), ("bs4", "beautifulsoup4"), ("PIL", "pillow")]:
        try:
            importlib.import_module(lib)
            print(f"\033[92m✓\033[0m {pkg}")
        except ImportError:
            print(f"\033[93m📦 Installing {pkg}...\033[0m", end=" ", flush=True)
            
            for cmd in [
                [sys.executable, "-m", "pip", "install", pkg, "--user", "-q"],
                ["pip3", "install", pkg, "--user", "-q"],
                [sys.executable, "-m", "pip", "install", pkg, "--break-system-packages", "-q"]
            ]:
                try:
                    subprocess.run(cmd, check=True, timeout=300, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                    importlib.invalidate_caches()
                    importlib.import_module(lib)
                    print(f"\033[92m✓\033[0m")
                    break
                except:
                    continue
            else:
                return False
    
    return True

if not ensure_packages():
    sys.exit(1)

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from PIL import Image

VERSION = "2.0.0"
AUTHOR = "Monayem Hossain"
GITHUB = "https://github.com/Monayem-Hossain"

R = "\033[91m"
G = "\033[92m"
Y = "\033[93m"
B = "\033[94m"
M = "\033[95m"
C = "\033[96m"
W = "\033[0m"
BOLD = "\033[1m"

SIMPLE_MODE = os.environ.get("SIMPLE_TERMINAL") == "1"

if SIMPLE_MODE:
    R = G = Y = B = M = C = W = BOLD = ""

state_lock = Lock()
session = requests.Session()

CONFIG_DIR = Path.home() / ".manga_downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "download.log"

DEFAULT_CONFIG = {
    "download_dir": str(Path.home() / "Manga"),
    "max_workers": 5,
    "timeout": 30,
    "retries": 3,
    "quality": 85,
    "auto_orient": True,
    "create_pdf": True,
    "delete_images": True,
    "color": True,
    "user_agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "sources": ["asurascans.com"],
    "output_format": "pdf"
}

config = {}
state = {}

def is_termux():
    return os.path.exists("/data/data/com.termux") or os.environ.get("TERMUX_APP") == "true"

def is_android():
    return is_termux() or os.environ.get("ANDROID_ROOT") is not None

def ensure_config():
    global config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    else:
        config = DEFAULT_CONFIG.copy()
        if is_termux():
            config["download_dir"] = "/storage/emulated/0/Manga"
            config["user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        save_config()
    
    os.makedirs(config["download_dir"], exist_ok=True)
    return config

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def load_state():
    global state
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
    else:
        state = {}
    return state

def save_state():
    with state_lock:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )

def check_installed_packages():
    missing = []
    for pkg, name in [("requests", "requests"), ("bs4", "beautifulsoup4"), ("PIL", "pillow")]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(name)
    
    if missing:
        print(f"{Y}Installing missing packages: {', '.join(missing)}{W}")
        for pkg in missing:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)
            except:
                pass
        print(f"{G}Packages ready{W}")

def install_packages_auto():
    check_installed_packages()

def banner():
    if SIMPLE_MODE:
        print("\n=== MANGA DOWNLOADER v{} ===\n".format(VERSION))
        return
    
    print(f"""
{C}╔═══════════════════════════════════════════════════════════╗
║   {W}{BOLD} █████╗ ███████╗██╗   ██║██████╗  █████╗ ██╗  ██╗{W}{C}    ║
║   {W}{BOLD}██╔══██╗██╔════╝██║   ██║██╔══██╗██╔══██╗╚██╗██╔╝{W}{C}    ║
║   {W}{BOLD}███████║███████╗██║   ██║██████╔╝███████║ ╚███╔╝ {W}{C}    ║
║   {W}{BOLD}██╔══██║╚════██║██║   ██║██╔══██╗██╔══██║ ██╔██╗ {W}{C}    ║
║   {W}{BOLD}██║  ██║███████║╚██████╔╝██║  ██║██║  ██║██╔╝ ██╗{W}{C}    ║
║   {W}{BOLD}╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝{W}{C}    ║
║                                                           ║
║   {W}{BOLD}MANGA DOWNLOADER v{VERSION}{W}{C}                                   ║
║                                                           ║
║   {Y}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{W}{C}  ║
║   {G}Author:{W}   {AUTHOR}{W}                               ║
║   {G}GitHub:{W}  {GITHUB}{W}                  ║
║   {G}Mode:{W}    {'Termux' if is_termux() else 'Desktop'}{W}                                     ║
╚═══════════════════════════════════════════════════════════╝{W}
""")

BASE_URLS = {
    "asurascans.com": "https://asurascans.com",
    "manga4life.com": "https://manga4life.com",
}

HEADERS_TEMPLATE = {
    "User-Agent": config.get("user_agent", DEFAULT_CONFIG["user_agent"]),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

def get_session():
    session.headers.update(HEADERS_TEMPLATE)
    return session

def make_request(url, method="GET", debug=False, **kwargs):
    kwargs.setdefault("timeout", config.get("timeout", 30))
    kwargs.setdefault("allow_redirects", True)
    
    for attempt in range(config.get("retries", 3)):
        try:
            if method == "GET":
                response = session.get(url, **kwargs)
            else:
                response = session.post(url, **kwargs)
            response.raise_for_status()
            if debug:
                print(f"DEBUG: Got {len(response.text)} chars from {url}")
            return response
        except Exception as e:
            logging.warning(f"Request attempt {attempt+1} failed: {e}")
            if attempt < config.get("retries", 3) - 1:
                time.sleep(1 * (attempt + 1))
            else:
                raise

def search_manga(query, source="asurascans.com"):
    base_url = BASE_URLS.get(source, source)
    if not base_url.startswith("http"):
        base_url = f"https://{source}"
    
    search_url = f"{base_url}/browse?search={quote(query)}"
    logging.info(f"Searching: {query} on {source}")
    
    try:
        response = make_request(search_url)
    except Exception as e:
        logging.error(f"Search failed: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen_urls = set()
    
    for item in soup.select(".grid > div"):
        link = item.select_one("a[href*='/comics/']")
        if not link:
            continue
        
        href = link.get("href", "")
        if "/chapter/" in href:
            continue
        
        if href in seen_urls:
            continue
        seen_urls.add(href)
        
        text = item.get_text(strip=True)
        title = re.sub(r'^\d+\.?\d*', '', text).strip()
        status = ""
        if re.search(r'(ongoing|completed|hiatus|dropped)', text, re.I):
            status = re.search(r'(ongoing|completed|hiatus|dropped)', text, re.I).group(1)
        chapters = ""
        ch_match = re.search(r'(\d+)\s*Chs?', text, re.I)
        if ch_match:
            chapters = ch_match.group(1)
        
        title = re.sub(r'\d+\s*Chs?.*', '', title, flags=re.I).strip()
        
        if title:
            if not href.startswith("http"):
                href = base_url + href
            results.append({"title": title, "url": href, "source": source, "chapters": chapters, "status": status})
    
    return results

def get_chapters(manga_url):
    try:
        response = make_request(manga_url)
    except Exception as e:
        logging.error(f"Failed to get chapters: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    chapters = []
    
    for a in soup.select("a[href*='/chapter/']"):
        href = a.get("href", "")
        text = a.get_text(separator=" ", strip=True)
        if href and text and "/chapter/" in href:
            match = re.search(r'chapter\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
            if match:
                ch_num = match.group(1)
                if ch_num not in [c["number"] for c in chapters]:
                    if href.startswith("http"):
                        chapters.append({"number": ch_num, "url": href})
                    else:
                        chapters.append({"number": ch_num, "url": "https://asurascans.com" + href})
    
    chapters.sort(key=lambda x: float(x["number"]))
    return chapters

def get_pages(chapter_url):
    try:
        response = make_request(chapter_url)
    except Exception as e:
        logging.error(f"Failed to get pages: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    pages = []
    
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-image")
        if src and "data:image" not in src and any(src.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
            if "cover" not in src.lower() and "logo" not in src.lower():
                pages.append(src)
    
    return list(dict.fromkeys(pages))

def download_image(url, path, retries=None):
    if retries is None:
        retries = config.get("retries", 3)
    
    for attempt in range(retries):
        try:
            response = make_request(url, stream=True)
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            time.sleep(0.3)
            return True
        except Exception as e:
            logging.warning(f"Download attempt {attempt+1} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(1)
    return False

def create_pdf_from_images(image_dir, output_path, quality=None):
    if quality is None:
        quality = config.get("quality", 85)
    
    images = []
    valid_files = []
    
    for f in sorted(os.listdir(image_dir)):
        fpath = os.path.join(image_dir, f)
        if not os.path.isfile(fpath):
            continue
        ext = f.lower().split('.')[-1]
        if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
            valid_files.append((f, fpath))
    
    if not valid_files:
        logging.error("No valid images found")
        return None
    
    converted = []
    
    for fname, fpath in valid_files:
        try:
            img = Image.open(fpath)
            
            if img.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            converted.append(img)
        except Exception as e:
            logging.warning(f"Failed to process {fname}: {e}")
            continue
    
    if not converted:
        logging.error("No images could be processed")
        return None
    
    try:
        from PIL import Image as PILImage
        first_img = converted[0]
        first_img.save(
            output_path,
            "PDF",
            save_all=True,
            append_images=converted[1:],
            resolution=100.0
        )
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logging.info(f"PDF created: {output_path}")
            return output_path
    except Exception as e:
        logging.error(f"PDF creation failed: {e}")
    
    return None

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def get_download_path(manga_name):
    download_dir = config.get("download_dir", str(Path.home() / "Manga"))
    
    if is_termux():
        for test_dir in ["/storage/emulated/0/Manga", "/sdcard/Manga", download_dir]:
            try:
                os.makedirs(test_dir, exist_ok=True)
                test_file = os.path.join(test_dir, ".test")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                download_dir = test_dir
                break
            except:
                continue
    
    return os.path.join(download_dir, sanitize_filename(manga_name))

def download_chapter(chapter_info, manga_name, base_path):
    ch_num = chapter_info["number"]
    ch_url = chapter_info["url"]
    
    safe_name = sanitize_filename(manga_name)
    chapter_dir = os.path.join(base_path, f"Chapter_{ch_num}")
    pdf_path = chapter_dir + ".pdf"
    
    if os.path.exists(pdf_path):
        logging.info(f"Chapter {ch_num} already downloaded")
        return "skipped"
    
    try:
        os.makedirs(chapter_dir, exist_ok=True)
    except Exception as e:
        logging.error(f"Cannot create directory: {e}")
        return "failed"
    
    pages = get_pages(ch_url)
    if not pages:
        logging.error(f"No pages found for chapter {ch_num}")
        return "failed"
    
    logging.info(f"Chapter {ch_num}: {len(pages)} pages")
    
    downloaded = 0
    max_workers = 2
    
    logging.info(f"Downloading {len(pages)} pages...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, url in enumerate(pages):
            ext = os.path.splitext(url.split("?")[0])[-1] or ".jpg"
            if len(ext) > 5:
                ext = ".jpg"
            filename = f"{i:03d}{ext}"
            fpath = os.path.join(chapter_dir, filename)
            
            if not os.path.exists(fpath):
                futures[executor.submit(download_image, url, fpath)] = i
        
        for future in as_completed(futures):
            if future.result():
                downloaded += 1
            else:
                logging.warning(f"Failed to download page")
    
    logging.info(f"Downloaded {downloaded}/{len(pages)} pages")
    
    if config.get("create_pdf", True):
        pdf_path = create_pdf_from_images(chapter_dir, pdf_path)
        if pdf_path and config.get("delete_images", True):
            try:
                shutil.rmtree(chapter_dir)
            except:
                pass
    
    return "downloaded" if pdf_path else "failed"

def parse_chapter_range(range_str, chapters):
    if not range_str or range_str.strip() == "":
        return chapters
    
    range_str = range_str.strip()
    
    if range_str.lower() in ["all", "*", "-1"]:
        return chapters
    
    if "-" in range_str:
        parts = range_str.split("-")
        try:
            start = float(parts[0].strip())
            end = float(parts[1].strip()) if len(parts) > 1 else float('inf')
            return [c for c in chapters if start <= float(c["number"]) <= end]
        except:
            pass
    else:
        try:
            num = float(range_str)
            return [c for c in chapters if float(c["number"]) == num]
        except:
            pass
    
    return chapters

def interactive_mode():
    banner()
    
    query = input(f"{C}📚 Enter manga name: {W}").strip()
    if not query:
        print(f"{R}❌ No input provided{W}")
        return
    
    source = config.get("sources", ["asurascans.com"])[0]
    results = search_manga(query, source)
    
    if not results:
        print(f"{R}❌ No results found{W}")
        return
    
    print(f"\n{C}📋 Results:{W}")
    for i, r in enumerate(results, 1):
        chapters = r.get("chapters", "")
        status = r.get("status", "")
        info = f"{chapters} Chapters {status}" if chapters or status else ""
        if info:
            print(f"{G}{i}.{W} {r['title']} - ({info})")
        else:
            print(f"{G}{i}.{W} {r['title']}")
    
    try:
        choice = int(input(f"\n{C}Select number: {W}"))
        if choice < 1 or choice > len(results):
            print(f"{R}Invalid selection{W}")
            return
        selected = results[choice - 1]
    except:
        print(f"{R}Invalid input{W}")
        return
    
    manga_name = selected["title"]
    manga_url = selected["url"]
    
    print(f"\n{G}Selected: {manga_name}{W}")
    print(f"{C}Fetching chapters...{W}")
    
    chapters = get_chapters(manga_url)
    if not chapters:
        print(f"{R}No chapters found{W}")
        return
    
    chapters.sort(key=lambda x: float(x["number"]))
    
    print(f"{C}Found {len(chapters)} chapters ({chapters[0]['number']} - {chapters[-1]['number']}){W}")
    
    range_input = input(f"{C}Chapter range (e.g., 1-10 or all): {W}").strip()
    selected_chapters = parse_chapter_range(range_input, chapters)
    
    if not selected_chapters:
        print(f"{R}No chapters in range{W}")
        return
    
    print(f"\n{C}Downloading {len(selected_chapters)} chapters...{W}")
    
    base_path = get_download_path(manga_name)
    os.makedirs(base_path, exist_ok=True)
    
    success = failed = skipped = 0
    
    for i, ch in enumerate(selected_chapters, 1):
        print(f"[{i}/{len(selected_chapters)}] Chapter {ch['number']}...", end=" ", flush=True)
        result = download_chapter(ch, manga_name, base_path)
        
        if result == "downloaded":
            print(f"{G}✓{W}")
            success += 1
        elif result == "skipped":
            print(f"{Y}⏭{W}")
            skipped += 1
        else:
            print(f"{R}✗{W}")
            failed += 1
        
        if i < len(selected_chapters):
            time.sleep(2)
    
    print(f"\n{G}✅ Complete! Downloaded: {success}, Skipped: {skipped}, Failed: {failed}{W}")
    print(f"{C}📁 Location: {base_path}{W}")

def auto_mode(manga_name, chapter_range="all", source="asurascans.com"):
    banner()
    
    print(f"{C}Auto mode: {manga_name}{W}")
    
    results = search_manga(manga_name, source)
    if not results:
        logging.error("No manga found")
        return False
    
    selected = results[0]
    manga_name = selected["title"]
    manga_url = selected["url"]
    
    logging.info(f"Manga: {manga_name}")
    
    chapters = get_chapters(manga_url)
    if not chapters:
        logging.error("No chapters found")
        return False
    
    chapters.sort(key=lambda x: float(x["number"]))
    selected_chapters = parse_chapter_range(chapter_range, chapters)
    
    if not selected_chapters:
        logging.error("No chapters in range")
        return False
    
    logging.info(f"Chapters: {len(selected_chapters)}")
    
    base_path = get_download_path(manga_name)
    os.makedirs(base_path, exist_ok=True)
    
    for i, ch in enumerate(selected_chapters, 1):
        logging.info(f"[{i}/{len(selected_chapters)}] Chapter {ch['number']}")
        download_chapter(ch, manga_name, base_path)
        time.sleep(2)
    
    logging.info(f"Done! Downloaded to: {base_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Manga Downloader CLI")
    parser.add_argument("manga", nargs="?", help="Manga name to search")
    parser.add_argument("-r", "--range", default="all", help="Chapter range (e.g., 1-10)")
    parser.add_argument("-s", "--source", default="asurascans.com", help="Manga source")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument("-a", "--auto", action="store_true", help="Auto mode (no prompts)")
    parser.add_argument("--config", action="store_true", help="Edit config")
    parser.add_argument("--list", action="store_true", help="List saved manga")
    parser.add_argument("--version", action="store_true", help="Show version")
    
    args = parser.parse_args()
    
    ensure_config()
    load_state()
    install_packages_auto()
    
    if args.version:
        print(f"Manga Downloader v{VERSION}")
        return
    
    if args.config:
        print(f"Config file: {CONFIG_FILE}")
        print(json.dumps(config, indent=2))
        return
    
    if args.list:
        print(f"\n{C}Downloaded Manga:{W}")
        download_dir = config.get("download_dir", str(Path.home() / "Manga"))
        if os.path.exists(download_dir):
            for d in os.listdir(download_dir):
                dpath = os.path.join(download_dir, d)
                if os.path.isdir(dpath):
                    pdfs = len([f for f in os.listdir(dpath) if f.endswith('.pdf')])
                    print(f"  {G}{d}{W}: {pdfs} chapters")
        return
    
    if args.output:
        config["download_dir"] = args.output
        save_config()
        print(f"Output set to: {args.output}")
        return
    
    if args.manga:
        auto_mode(args.manga, args.range, args.source)
    else:
        interactive_mode()

if __name__ == "__main__":
    main()
