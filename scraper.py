#!/usr/bin/env python3
"""
Scrapes Falter.at recommended films for Vienna, fetches showtimes and details
for a random selection, and POSTs to the TRMNL webhook.

Run frequently (e.g. every 30-60 min) for rotation. The full film list
(without showtimes/details) is cached daily; only the 4 selected films trigger
detail-page fetches per run.

Required env var: TRMNL_WEBHOOK_URL
"""
import json
import os
import random
import re
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TRMNL_WEBHOOK_URL = os.environ["TRMNL_WEBHOOK_URL"]
CACHE_FILE = Path(__file__).parent / "films_cache.json"
DISPLAY_COUNT = 4   # 2×2 quadrants on TRMNL
PAGES_TO_FETCH = 7
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_SHOWTIMES = 3   # next N showtimes per film


def get_text(el):
    return el.get_text(strip=True) if el else ""


def parse_films(html):
    soup = BeautifulSoup(html, "html.parser")
    films = []
    for a in soup.select("a.group.block"):
        href = a.get("href", "")
        if not re.search(r"/kino/\d+/", href):
            continue
        title = get_text(a.select_one("h2"))
        if not title:
            continue
        year = get_text(a.select_one("div.text-xl.font-normal")).strip("()")
        uls = a.select("ul.font-display")
        director = ""
        if uls:
            for li in uls[0].select("li"):
                text = get_text(li)
                if text and not text.startswith("OT:"):
                    director = text
                    break
        country, runtime = "", ""
        if len(uls) >= 2:
            items = [get_text(li) for li in uls[1].select("li")]
            country = items[0] if items else ""
            runtime = items[1] if len(items) > 1 else ""
        genres = [get_text(li) for li in a.select("li.bg-gray-50") if get_text(li)]

        # Extract poster image from the film card thumbnail
        poster_url = ""
        poster_img = a.select_one("img[src*=\"/events/\"]")
        if poster_img:
            src = poster_img.get("src", "")
            # Use a larger size (300px) for the TRMNL display
            poster_url = re.sub(r"/events/\d+/", "/events/300/", src)

        films.append({
            "t": title,
            "y": year,
            "d": director,
            "g": " / ".join(genres),
            "c": f"{country} {runtime}".strip(),
            "p": poster_url,
            "url": href,
        })
    return films


def fetch_details(film_url):
    """Fetch showtimes and description from a film's detail page.

    Returns (showtimes_list, description_string).
    """
    resp = requests.get(film_url, timeout=15, headers=HEADERS)
    if not resp.ok:
        return [], ""
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract short description from meta tag
    meta_desc = soup.select_one("meta[name=description]")
    description = meta_desc.get("content", "").strip() if meta_desc else ""
    # Truncate for payload and display — keep ~100 chars at a word boundary
    if len(description) > 100:
        cutoff = description.rfind(" ", 0, 97)
        if cutoff > 60:
            description = description[:cutoff] + "..."
        else:
            description = description[:97] + "..."

    # Extract showtimes from timetable
    timetable = soup.find(id="timetable")
    showtimes = []
    if timetable:
        for tbody in timetable.select("tbody[data-region]"):
            th = tbody.select_one("th div.block")
            cinema = get_text(th)
            for row in tbody.select("tr")[1:]:
                tds = row.select("td")
                if len(tds) < 2:
                    continue
                raw_date = get_text(tds[0])
                date_match = re.search(r"(\d{2}\.\d{2}\.)", raw_date)
                day_match = re.search(r"(Mo|Di|Mi|Do|Fr|Sa|So)", raw_date)
                short_date = date_match.group(1) if date_match else raw_date[:6]
                day = day_match.group(1) if day_match else ""
                time_raw = get_text(tds[1])
                time_match = re.search(r"\d{2}:\d{2}", time_raw)
                time = time_match.group(0) if time_match else time_raw
                if cinema and time:
                    showtimes.append({
                        "k": cinema,
                        "dat": f"{day} {short_date}".strip(),
                        "ti": time,
                    })
                if len(showtimes) >= MAX_SHOWTIMES:
                    return showtimes, description
    return showtimes, description


def scrape_films(span):
    all_films = []
    for page in range(1, PAGES_TO_FETCH + 1):
        url = (
            f"https://www.falter.at/kino/suche"
            f"?region=Wien&is_recommended=true&span={span}&page={page}"
        )
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        page_films = parse_films(resp.text)
        if not page_films:
            break
        all_films.extend(page_films)
    return all_films


def load_films(today):
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text())
        if cache.get("date") == str(today):
            print(f"Using cache ({len(cache['films'])} films).")
            return cache["films"]
    end = today + timedelta(days=6)
    span = f"{today}%3A{end}"
    print("Fetching from falter.at...")
    films = scrape_films(span)
    CACHE_FILE.write_text(json.dumps({"date": str(today), "films": films}))
    print(f"Cached {len(films)} films.")
    return films


def main():
    today = date.today()
    all_films = load_films(today)
    if not all_films:
        print("No films found, aborting.")
        return

    selection = random.sample(all_films, min(DISPLAY_COUNT, len(all_films)))

    print(f"Fetching details for {len(selection)} films...")
    for film in selection:
        showtimes, desc = fetch_details(film["url"])
        film["s"] = showtimes
        if desc:
            film["desc"] = desc
        del film["url"]  # don't waste payload space

    payload = {
        "merge_variables": {
            "films": selection,
            "week": today.strftime("%-d. %b"),
        }
    }

    size = len(json.dumps(payload))
    print(f"Posting {len(selection)} films ({size} bytes).")
    if size > 2000:
        print("WARNING: payload over 2kb, TRMNL may reject it.")

    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, timeout=10)
    print(f"TRMNL: {resp.status_code} {resp.text}")


if __name__ == "__main__":
    main()
