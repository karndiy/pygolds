import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# Config
GTO_URL = 'https://classic.goldtraders.or.th/UpdatePriceList.aspx'
POST_URL = 'https://karndiy.pythonanywhere.com/cjson/goldjson-v2'
DATA_DIR = Path("data")
OUT_JSON = DATA_DIR / "gold_prices.json"

# เพิ่ม Header ที่สำคัญเพื่อเลี่ยง 403 Forbidden
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://classic.goldtraders.or.th/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

def xnowtime():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def save_to_json(data, filepath: Path):
    ensure_dir(filepath.parent)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_be_datetime(s: str):
    try:
        date_part, time_part = s.split()
        d, m, y_be = date_part.split("/")
        y_ce = int(y_be) - 543
        dt = datetime.strptime(f"{d}/{m}/{y_ce} {time_part}", "%d/%m/%Y %H:%M")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def scrape_gold_data(url=GTO_URL, retries=3, backoff=2, timeout=15):
    last_err = None
    for attempt in range(1, retries+1):
        try:
            print(f"[{xnowtime()}] Attempt {attempt}/{retries} connecting to {url}...")
            # เพิ่ม timeout เล็กน้อยเพื่อให้ server ประมวลผลได้
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            res.raise_for_status()
            res.encoding = "utf-8"
            
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find("table", {"id": "DetailPlace_MainGridView"})
            
            if not table:
                print(f"[{xnowtime()}] Error: Table not found!")
                return []

            rows = table.find_all("tr")
            data = []
            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) >= 9:
                    asdate = cols[0].get_text(strip=True)
                    item = {
                        'asdate': asdate,
                        'nqy': cols[1].get_text(strip=True),
                        'blbuy': cols[2].get_text(strip=True),
                        'blsell': cols[3].get_text(strip=True),
                        'ombuy': cols[4].get_text(strip=True),
                        'omsell': cols[5].get_text(strip=True),
                        'goldspot': cols[6].get_text(strip=True),
                        'bahtusd': cols[7].get_text(strip=True),
                        'diff': cols[8].get_text(strip=True),
                    }
                    iso = parse_be_datetime(asdate)
                    if iso:
                        item['asdate_iso'] = iso
                    data.append(item)

            return data[::-1]
        except Exception as e:
            last_err = e
            print(f"[{xnowtime()}] Attempt {attempt} failed: {e}")
            time.sleep(backoff ** attempt)
            
    print(f"[{xnowtime()}] Final failure: {last_err}")
    return []

def post_data(url: str, payload):
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=15)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)

def main():
    data = scrape_gold_data()
    if not data:
        print("No data scraped, aborting.")
        return 2

    save_to_json(data, OUT_JSON)
    status, body = post_data(POST_URL, data)
    
    if status == 201:
        print(f"[{xnowtime()}] POST OK 201")
        return 0
    else:
        print(f"[{xnowtime()}] POST failed: {status} - {body[:300]}...")
        return 4

if __name__ == "__main__":
    sys.exit(main())