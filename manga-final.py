#!/usr/bin/env python3
import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import shutil
from concurrent.futures import ThreadPoolExecutor
import time

BASE_URL = "https://asurascans.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL
}

session = requests.Session()
session.headers.update(HEADERS)

def search_manga(query):
    print(f"\nSearching for: {query}")
    search_url = f"{BASE_URL}/browse?search={quote(query)}"
    
    response = session.get(search_url, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen_titles = set()
    seen_urls = set()
    
    for item in soup.select(".grid > div"):
        link = item.select_one("a[href*='/comics/']")
        if not link:
            continue
        
        href = link.get("href", "")
        if "/chapter/" in href:
            continue
        
        text = item.get_text(strip=True)
        title = re.sub(r'^\d+\.\d+', '', text).strip()
        title = re.sub(r'\d+Chs\.Chapters.*$', '', title).strip()
        
        if title and title.lower() not in seen_titles and href not in seen_urls:
            seen_titles.add(title.lower())
            seen_urls.add(href)
            if not href.startswith("http"):
                href = BASE_URL + href
            results.append({"title": title, "url": href})
    
    if not results:
        print("No results found")
    
    return results

def get_chapter_list(manga_url):
    response = session.get(manga_url, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    chapters = []
    
    for a in soup.select("a[href*='/chapter/']"):
        href = a.get("href", "")
        text = a.get_text(separator=" ", strip=True)
        if href and text:
            match = re.search(r'chapter\s*(\d{1,3})', text, re.IGNORECASE)
            if match:
                chapter_num = match.group(1)
                if chapter_num not in [c["number"] for c in chapters]:
                    if not href.startswith("http"):
                        href = BASE_URL + href
                    chapters.append({"number": chapter_num, "url": href})
    
    if not chapters:
        for a in soup.select("a[href*='/chapters/']"):
            href = a.get("href", "")
            text = a.get_text(separator=" ", strip=True)
            if href and text:
                match = re.search(r'chapter\s*(\d{1,3})', text, re.IGNORECASE)
                if match:
                    chapter_num = match.group(1)
                    if chapter_num not in [c["number"] for c in chapters]:
                        if not href.startswith("http"):
                            href = BASE_URL + href
                        chapters.append({"number": chapter_num, "url": href})
    
    return chapters

def get_chapter_pages(chapter_url):
    response = session.get(chapter_url, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    pages = []
    
    for img in soup.select("img.w-full"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src and "data:image" not in src:
            pages.append(src)
    
    if not pages:
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "images" in script_text.lower() or "pages" in script_text.lower():
                urls = re.findall(r'["\'](https?://[^"\'\s]+\.(?:jpg|jpeg|png|webp))["\']', script_text)
                pages.extend(urls)
    
    return pages

def download_image(url, save_path, retries=3):
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            print(f"Failed to download {url}: {e}")
            return False
    return False

def download_chapter(chapter_info, manga_name, output_dir):
    chapter_num = chapter_info["number"]
    chapter_url = chapter_info["url"]
    
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', manga_name)
    safe_num = re.sub(r'[<>:"/\\|?*]', '_', chapter_num)
    chapter_folder = os.path.join(output_dir, f"{safe_name}_Chapter_{safe_num}")
    pdf_path = chapter_folder + ".pdf"
    
    if os.path.exists(pdf_path):
        print(f"Chapter {chapter_num} PDF already exists, skipping...")
        return None
    
    if os.path.exists(chapter_folder):
        print(f"Chapter {chapter_num} folder exists, converting to PDF...")
        return chapter_folder
    
    print(f"\nDownloading Chapter {chapter_num}...")
    os.makedirs(chapter_folder, exist_ok=True)
    
    pages = get_chapter_pages(chapter_url)
    if not pages:
        print(f"No pages found for chapter {chapter_num}")
        os.rmdir(chapter_folder)
        return None
    
    print(f"Found {len(pages)} pages")
    print("Downloading pages: ", end="", flush=True)
    
    def download_page(idx_url):
        idx, url = idx_url
        ext = os.path.splitext(url.split("?")[0])[-1] or ".jpg"
        if len(ext) > 5:
            ext = ".jpg"
        filename = f"{idx:03d}{ext}"
        result = download_image(url, os.path.join(chapter_folder, filename))
        sys.stdout.write(".")
        sys.stdout.flush()
        return result
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [(i, url) for i, url in enumerate(pages)]
        results = list(executor.map(lambda x: download_page(x), futures))
    
    print(f" done ({sum(results)}/{len(results)} pages)")
    
    if not any(results):
        print(f"No pages downloaded for chapter {chapter_num}")
        shutil.rmtree(chapter_folder, ignore_errors=True)
        return None
    
    return chapter_folder

def create_pdf(chapter_folder):
    try:
        from img2pdf import convert
        from PIL import Image
    except ImportError:
        print("img2pdf not installed. Attempting to install...")
        try:
            import subprocess
            subprocess.check_call(["pip", "install", "img2pdf", "pillow", "-q"])
            from img2pdf import convert
            from PIL import Image
            print("img2pdf installed successfully.")
        except Exception as e:
            print(f"Failed to install img2pdf: {e}")
            return None
    
    images = []
    temp_jpgs = []
    
    for fname in sorted(os.listdir(chapter_folder)):
        fpath = os.path.join(chapter_folder, fname)
        if not os.path.isfile(fpath):
            continue
        
        ext = fname.lower().split('.')[-1]
        
        if ext in ("jpg", "jpeg", "png"):
            images.append(fpath)
        elif ext == "webp":
            try:
                jpg_path = fpath.replace(".webp", ".jpg")
                img = Image.open(fpath)
                if img.mode == "RGBA":
                    img = img.convert("RGB")
                img.save(jpg_path, "JPEG")
                images.append(jpg_path)
                temp_jpgs.append(jpg_path)
            except Exception as e:
                print(f"Failed to convert {fname}: {e}")
                continue
    
    if not images:
        print("No valid images found in chapter folder.")
        return None
    
    try:
        pdf_data = convert(images)
        pdf_path = chapter_folder + ".pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_data)
        
        for jpg in temp_jpgs:
            try:
                os.remove(jpg)
            except:
                pass
        
        return pdf_path
    except Exception as e:
        print(f"PDF creation error: {e}")
        return None

def create_pdf_fallback(chapter_folder):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from PIL import Image
    except ImportError:
        print("reportlab/pillow not installed. Skipping PDF.")
        print("To enable PDF, run: pip install reportlab pillow")
        return None
    
    images = []
    for fname in sorted(os.listdir(chapter_folder)):
        fpath = os.path.join(chapter_folder, fname)
        if os.path.isfile(fpath) and fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            images.append(fpath)
    
    if not images:
        return None
    
    pdf_path = chapter_folder + ".pdf"
    c = canvas.Canvas(pdf_path, pagesize=letter)
    
    for img_path in images:
        try:
            img = Image.open(img_path)
            width, height = img.size
            dpi = 72
            c.setPageSize((width * dpi / 96, height * dpi / 96))
            c.drawImage(img_path, 0, 0, width=width * dpi / 96, height=height * dpi / 96)
            c.showPage()
        except Exception as e:
            print(f"Error adding {img_path}: {e}")
    
    c.save()
    return pdf_path

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║                                                                  ║
║                        M  A  N  G  A                             ║
║                  D  O  W  N  L  O  A  D  E  R                    ║
║                                                                  ║
║                        [ AsuraScans ]                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

def main():
    print(BANNER)
    
    query = input("\nEnter manga name to search: ").strip()
    if not query:
        print("No query provided")
        return
    
    results = search_manga(query)
    
    if not results:
        print("No manga found")
        return
    
    print("\nSearch Results:")
    print("-" * 40)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
    print("-" * 40)
    
    try:
        choice = int(input("Select manga number: "))
        if choice < 1 or choice > len(results):
            print("Invalid selection")
            return
        selected = results[choice - 1]
    except ValueError:
        print("Invalid input")
        return
    
    manga_name = selected["title"]
    manga_url = selected["url"]
    print(f"\nSelected: {manga_name}")
    
    print("\nFetching chapter list...")
    chapters = get_chapter_list(manga_url)
    
    if not chapters:
        print("No chapters found")
        return
    
    chapters.sort(key=lambda x: float(x["number"]))
    
    print(f"Found {len(chapters)} chapters")
    print(f"First chapter: {chapters[0]['number']}")
    print(f"Last chapter: {chapters[-1]['number']}")
    
    range_input = input("\nEnter chapter range (e.g., 1-10 or 5): ").strip()
    
    start_chapter, end_chapter = None, None
    
    if "-" in range_input:
        parts = range_input.split("-")
        try:
            start_chapter = float(parts[0].strip())
            end_chapter = float(parts[1].strip())
        except ValueError:
            print("Invalid range format")
            return
    else:
        try:
            start_chapter = end_chapter = float(range_input)
        except ValueError:
            print("Invalid chapter number")
            return
    
    selected_chapters = [c for c in chapters 
                        if start_chapter <= float(c["number"]) <= end_chapter]
    
    if not selected_chapters:
        print("No chapters in range")
        return
    
    print(f"\nWill download {len(selected_chapters)} chapters")
    
    output_dir = os.path.join(os.getcwd(), re.sub(r'[<>:"/\\|?*]', '_', manga_name))
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    downloaded = 0
    skipped = 0
    failed = 0
    
    for i, chapter in enumerate(selected_chapters, 1):
        print(f"\n[{i}/{len(selected_chapters)}] Processing chapter {chapter['number']}")
        
        chapter_folder = download_chapter(chapter, manga_name, output_dir)
        
        if chapter_folder and os.path.exists(chapter_folder):
            print("Converting to PDF...")
            pdf_path = create_pdf(chapter_folder)
            
            if pdf_path and os.path.exists(pdf_path):
                print(f"PDF saved: {pdf_path}")
                print("Deleting chapter folder...")
                shutil.rmtree(chapter_folder, ignore_errors=True)
                downloaded += 1
            else:
                print("PDF creation failed, keeping chapter folder")
                failed += 1
        elif chapter_folder is None:
            print(f"Skipping chapter {chapter['number']}")
            skipped += 1
    
    pdf_count = len([f for f in os.listdir(output_dir) if f.endswith(".pdf")])
    
    print("\n" + "=" * 50)
    print("Download complete!")
    print(f"PDFs saved: {pdf_count}")
    print(f"Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}")
    print(f"Output directory: {output_dir}")
    print("=" * 50)

if __name__ == "__main__":
    main()
