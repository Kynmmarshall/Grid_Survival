"""
Download game assets for Grid Survival.
"""

import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"

OBSTACLES_DIR = ASSETS_DIR / "Obstacles"
HAZARDS_DIR = ASSETS_DIR / "Hazards"

ASSETS = [
    ("hazards", "https://opengameart.org/sites/default/files/Snake%20sprite%20sheet.png"),
    ("hazards", "https://opengameart.org/sites/default/files/DungeonSpider.png"),
    ("obstacles", "https://opengameart.org/sites/default/files/crate.png"),
]

def ensure_dirs():
    OBSTACLES_DIR.mkdir(parents=True, exist_ok=True)
    HAZARDS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Directories: {OBSTACLES_DIR}, {HAZARDS_DIR}")

def download_asset(asset_type: str, url: str) -> bool:
    dest_dir = OBSTACLES_DIR if asset_type == "obstacles" else HAZARDS_DIR
    filename = url.split("/")[-1].replace("%20", " ")
    dest = dest_dir / filename
    
    if dest.exists():
        print(f"  Exists: {filename}")
        return True
    
    try:
        print(f"  Downloading: {filename}...")
        urllib.request.urlretrieve(url, dest)
        print(f"  Saved: {dest}")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    print("=== Grid Survival Asset Downloader ===")
    ensure_dirs()
    
    for asset_type, url in ASSETS:
        print(f"\n[{asset_type.upper()}]")
        download_asset(asset_type, url)
    
    print("\n=== Done ===")
    print(f"Obstacles: {list(OBSTACLES_DIR.iterdir())}")
    print(f"Hazards: {list(HAZARDS_DIR.iterdir())}")

if __name__ == "__main__":
    main()