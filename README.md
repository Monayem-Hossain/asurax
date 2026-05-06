# AsuraScans Manga Downloader

A Python CLI tool to search and download manga chapters from AsuraScans as PDF files.

## Features

- Search manga by title
- List available chapters
- Download chapters in parallel
- Convert images to PDF
- Support for chapter range selection
## Install
```
git clone https://github.com/Monayem-Hossain/asurax-linux
```
## Requirements

```bash
pip install requests beautifulsoup4 img2pdf pillow
```

## Usage
```
cd asurax-linux
```
```
python -m venv myenv
source myenv/bin/activate
```
```bash
python main.py
```

1. Enter manga name to search
2. Select manga from results
3. Enter chapter range (e.g., `1-10` or `5`)
4. PDFs are saved in a folder with the manga name

## Output

- PDFs are saved in `{manga_name}/` directory
- Each chapter becomes a separate PDF file

## License

MIT
