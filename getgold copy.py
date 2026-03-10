# getgold.py  (refactor: robust + clear exit code)
import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

GTO_URL = 'https://classic.goldtraders.or.th/UpdatePriceList.aspx' #'https://www.goldtraders.or.th/UpdatePriceList.aspx'
POST_URL = 'https://karndiy.pythonanywhere.com/cjson/goldjson-v2'
DATA_DIR = Path("data")
OUT_JSON = DATA_DIR / "gold_prices.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
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
    """
    รับรูปแบบ '28/10/2568 09:25' (วัน/เดือน/ปีพ.ศ. เวลา)
    คืนค่า iso8601 (ปีคริสต์ศักราช) เช่น '2025-10-28 09:25:00'
    ถ้าแปลงไม่ได้ คืน None
    """
    try:
        date_part, time_part = s.split()
        d, m, y_be = date_part.split("/")
        y_ce = int(y_be) - 543
        dt = datetime.strptime(f"{d}/{m}/{y_ce} {time_part}", "%d/%m/%Y %H:%M")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def scrape_gold_data(url=GTO_URL, retries=3, backoff=1.5, timeout=12):
    last_err = None
    for attempt in range(1, retries+1):
        try:
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            res.raise_for_status()
            res.encoding = "utf-8"
            soup = BeautifulSoup(res.text, 'html.parser')

            table = soup.find("table", {"id": "DetailPlace_MainGridView"})
            if not table:
                print(f"[{xnowtime()}] Table not found (id=DetailPlace_MainGridView)")
                return []

            rows = table.find_all("tr")
            if len(rows) <= 1:
                print(f"[{xnowtime()}] No data rows in table")
                return []

            data = []
            for row in rows[1:]:  # skip header
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
                    # เพิ่มฟิลด์วันที่แบบ ค.ศ. เผื่อใช้งานภายหลัง (ไม่ไปกระทบโครงสร้างเดิม)
                    iso = parse_be_datetime(asdate)
                    if iso:
                        item['asdate_iso'] = iso
                    data.append(item)

            # เรียงล่าสุด→เก่าสุด ตามโค้ดเดิม
            data = data[::-1]
            return data
        except Exception as e:
            last_err = e
            print(f"[{xnowtime()}] Attempt {attempt}/{retries} scrape error: {e}")
            if attempt < retries:
                time.sleep(backoff ** attempt)
    print(f"[{xnowtime()}] Error while scraping (final): {last_err}")
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
        # บันทึกไฟล์ว่างไว้เผื่อ debug
        save_to_json([], OUT_JSON)
        return 2  # exit code != 0 เพื่อให้ .bat ทราบว่าล้มเหลว

    # บันทึก local ก่อน (กัน POST ล้มเหลวแล้วไม่มีไฟล์)
    save_to_json(data, OUT_JSON)
    print(f"[{xnowtime()}] Saved {len(data)} records to {OUT_JSON}")

    status, body = post_data(POST_URL, data)
    if status == 201:
        print(f"[{xnowtime()}] POST OK 201")
        # พิมพ์ข้อมูล (แบบเดิม) ถ้าต้องการให้ batch เห็นผลลัพธ์
        print(data)
        return 0
    elif status is None:
        print(f"[{xnowtime()}] POST failed: {body}")
        return 3
    else:
        print(f"[{xnowtime()}] POST error: HTTP {status} - {body[:300]}...")
        # ยังถือว่าล้มเหลวเพื่อให้ batch หยุดตามเงื่อนไขคุณ
        return 4

if __name__ == "__main__":
    sys.exit(main())