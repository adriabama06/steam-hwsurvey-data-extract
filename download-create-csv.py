#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Steam Hardware Survey Scraper
Extracts data from the Steam Hardware Survey subpages and saves it to CSVs.

Sources:
- Monthly history subpages (with MAY-SEP columns):
  - videocard (graphics cards)
  - directx (DirectX versions)
  - processormfg (CPU manufacturers)
  - cpus (number of CPUs per computer)
- Main page (https://store.steampowered.com/hwsurvey/) bottom table (#main_stats).
  This page has no month history, only current percentage + change.
  Each expandable row (submenu shown on click) is split into its own CSV:
  - osversion -> os.csv
  - System RAM -> ram.csv
  - Intel CPU Speeds -> cpu_speed.csv
  - Physical CPUs -> physical_cpus.csv
  - Video Card Description -> videocard_desc.csv
  - VRAM -> vram.csv
  - Primary Display Resolution -> monres.csv
  - Multi-Monitor Desktop Resolution -> multimon.csv
  - Language -> language.csv
  - Free Hard Drive Space -> disk_free.csv
  - Total Hard Drive Space -> disk_total.csv
  - VR Headsets -> vr_headsets.csv
  - Other Settings -> other_settings.csv

Usage: python download-create-csv.py
"""

import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import time
from datetime import datetime

# Configuration
BASE_URL = "https://store.steampowered.com/hwsurvey"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

# Monthly history subpages that really exist (with substats_row tables).
# NOTE: 'processor', 'os', 'ram', 'diskpace', 'monitortype', 'monres',
# 'multimon', etc. do NOT exist as standalone pages (they return the
# main page). Those categories are extracted from the main page instead.
SUBPAGES = {
    'videocard': 'videocard.csv',
    'directx': 'directx.csv',
    'processormfg': 'processormfg.csv',
    'cpus': 'cpus.csv',
}

# Main page (/) split: details div id -> (csv filename, category slug, fallback label).
# The slug is used as first CSV column header.
MAIN_PAGE_SPLIT = {
    'osversion_details': ('os.csv', 'os', 'OS Version'),
    'cat0_details': ('ram.csv', 'ram', 'System RAM'),
    'cat1_details': ('cpu_speed.csv', 'cpu_speed', 'Intel CPU Speeds'),
    'cat2_details': ('physical_cpus.csv', 'physical_cpus', 'Physical CPUs'),
    'cat3_details': ('videocard_desc.csv', 'videocard_desc', 'Video Card Description'),
    'cat4_details': ('vram.csv', 'vram', 'VRAM'),
    'cat5_details': ('monres.csv', 'monres', 'Primary Display Resolution'),
    'cat6_details': ('multimon.csv', 'multimon', 'Multi-Monitor Desktop Resolution'),
    'cat7_details': ('language.csv', 'language', 'Language'),
    'cat8_details': ('disk_free.csv', 'disk_free', 'Free Hard Drive Space'),
    'cat9_details': ('disk_total.csv', 'disk_total', 'Total Hard Drive Space'),
    'cat10_details': ('vr_headsets.csv', 'vr_headsets', 'VR Headsets'),
    'cat11_details': ('other_settings.csv', 'other_settings', 'Other Settings'),
}

# Month names that will appear as columns (It may change in the future, manually edit this to match the web)
MONTHS = ['MAY', 'JUN', 'JUL', 'AUG', 'SEP']


def fetch_page(url):
    """Downloads the HTML content of a page. Returns BeautifulSoup or None."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"  Error downloading {url}: {e}")
        return None


def extract_section_name(element):
    """
    Extracts the section name from the header.
    Headers have the 'col_header' and 'substats_col_left' classes.
    """
    text = element.get_text(strip=True)
    # Clean up text
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_row_data(row):
    """
    Extracts data from a substats_row row.
    Returns a dictionary with: name, month values, last month change.
    """
    data = {}

    # Item name (first column)
    name_elem = row.find('div', class_='substats_col_left')
    if name_elem:
        name = name_elem.get_text(strip=True)
        # Clean up name (remove possible line breaks)
        name = re.sub(r'\s+', ' ', name).strip()
        data['name'] = name
    else:
        return None

    # Previous month values (substats_col_month)
    month_values = []
    for month_elem in row.find_all('div', class_='substats_col_month'):
        value = month_elem.get_text(strip=True)
        # Remove % and spaces
        value = value.replace('%', '').strip()
        if value == '-' or value == '':
            value = 'N/A'
        month_values.append(value)

    # Last month value (substats_col_month_last_pct)
    last_pct_elem = row.find('div', class_='substats_col_month_last_pct')
    if last_pct_elem:
        last_pct = last_pct_elem.get_text(strip=True)
        last_pct = last_pct.replace('%', '').strip()
        month_values.append(last_pct)
    else:
        month_values.append('N/A')

    # Last month change (substats_col_month_last_chg)
    last_chg_elem = row.find('div', class_='substats_col_month_last_chg')
    if last_chg_elem:
        last_chg = last_chg_elem.get_text(strip=True)
        last_chg = last_chg.replace('%', '').strip()
    else:
        last_chg = 'N/A'

    data['months'] = month_values
    data['change'] = last_chg

    return data


def extract_table_data(soup):
    """
    Extracts the entire data table from a monthly subpage.
    Returns a list of sections, each with its name and data rows.
    """
    page_content = soup.find('div', class_='page_content')
    if not page_content:
        print("  page_content not found")
        return []

    # Look for the main data container
    main_div = None
    for div in page_content.find_all('div', recursive=False):
        children = list(div.find_all(recursive=False))
        if len(children) > 10:  # The main container has many children
            main_div = div
            break

    if not main_div:
        print("  Main container not found")
        return []

    # Iterate over all direct children in order
    direct_children = list(main_div.find_all(recursive=False))

    sections = []
    current_section = None
    current_section_name = None

    for child in direct_children:
        classes = child.get('class', [])

        # Detect section header (has col_header)
        if 'col_header' in classes and 'substats_col_left' in classes:
            section_name = extract_section_name(child)
            # Ignore the last change in the header (it is empty)
            if section_name:
                current_section_name = section_name
                current_section = []
                sections.append({
                    'name': current_section_name,
                    'rows': current_section
                })

        # Detect data row
        elif 'substats_row' in classes:
            if current_section is not None:
                row_data = extract_row_data(child)
                if row_data:
                    current_section.append(row_data)

    return sections


def _clean_pct(text):
    """Cleans a percentage cell: strips %, whitespace. Keeps numeric string."""
    if text is None:
        return 'N/A'
    value = re.sub(r'\s+', ' ', text).strip().replace('%', '').strip()
    if value == '' or value == '-':
        return 'N/A'
    return value


def _clean_change(text):
    """Cleans a change cell: strips %, keeps +/- sign."""
    if text is None:
        return 'N/A'
    value = re.sub(r'\s+', ' ', text).strip().replace('%', '').strip()
    if value == '':
        return 'N/A'
    return value


def extract_main_stats(soup):
    """
    Extracts the bottom summary table (#main_stats) from the main / page,
    including the expandable submenu details (stats_row_details).

    Only looks inside div#main_stats, so top graphs are ignored.
    Returns a dict: details_id -> {label, summary, rows}, where rows is a
    list of {name, pct, change, is_subheader}.
    """
    main_stats = soup.find('div', id='main_stats')
    if not main_stats:
        print("  main_stats table not found (expected div#main_stats)")
        return {}

    # Top-level summary rows are direct children with class stats_row
    summary_rows = [
        c for c in main_stats.find_all(recursive=False)
        if c.name == 'div' and 'stats_row' in (c.get('class', []))
    ]

    result = {}
    for summary in summary_rows:
        row_id = summary.get('id', '')
        # Derive details id: e.g. osversion_stats_row -> osversion_details,
        # cat0_stats_row -> cat0_details
        if row_id.endswith('_stats_row'):
            details_id = row_id.replace('_stats_row', '_details')
            # Special case is already covered: osversion_stats_row -> osversion_details
        else:
            continue

        left = summary.find('div', class_='stats_col_left')
        mid = summary.find('div', class_='stats_col_mid')
        right = summary.find('div', class_='stats_col_right')
        right2 = summary.find('div', class_='stats_col_right2')
        label = left.get_text(strip=True) if left else details_id

        summary_data = {
            'label': re.sub(r'\s+', ' ', label).strip(),
            'most_popular': mid.get_text(strip=True) if mid else '',
            'pct': _clean_pct(right.get_text(strip=True) if right else ''),
            'change': _clean_change(right2.get_text(strip=True) if right2 else ''),
        }

        details = soup.find('div', id=details_id)
        if not details:
            print(f"  Details block not found: {details_id}")
            continue

        rows = _parse_main_details(details)
        result[details_id] = {
            'label': summary_data['label'],
            'summary': summary_data,
            'rows': rows,
        }

    return result


def _parse_main_details(details):
    """
    Parses one div.stats_row_details block.
    Handles both subgroup headers (nested div.stats_row, e.g. Windows/OSX/Linux)
    and flat data rows (left/mid/right/right2 sequence).
    """
    rows = []
    # Direct children in order, skipping <br> tags
    children = [c for c in details.find_all(recursive=False) if getattr(c, 'name', None) == 'div']

    i = 0
    while i < len(children):
        child = children[i]
        classes = child.get('class', [])

        # Subgroup header: <div class="stats_row"> with nested mid/right/right2
        if 'stats_row' in classes:
            mid = child.find('div', class_='stats_col_mid')
            right = child.find('div', class_='stats_col_right')
            right2 = child.find('div', class_='stats_col_right2')
            if mid:
                name = re.sub(r'\s+', ' ', mid.get_text(strip=True)).strip()
                if name and name != '&nbsp;':
                    rows.append({
                        'name': name,
                        'pct': _clean_pct(right.get_text(strip=True) if right else ''),
                        'change': _clean_change(right2.get_text(strip=True) if right2 else ''),
                        'is_subheader': True,
                    })
            i += 1
            continue

        # Data row start: <div class="stats_col_mid data_row">
        if 'stats_col_mid' in classes:
            name = re.sub(r'\s+', ' ', child.get_text(strip=True)).strip()
            # Look ahead for pct (stats_col_right) and change (stats_col_right2)
            pct = 'N/A'
            change = 'N/A'
            for j in range(i + 1, min(i + 4, len(children))):
                sib_classes = children[j].get('class', [])
                if 'stats_col_right2' in sib_classes and change == 'N/A':
                    change = _clean_change(children[j].get_text(strip=True))
                elif 'stats_col_right' in sib_classes and pct == 'N/A':
                    pct = _clean_pct(children[j].get_text(strip=True))
            if name:
                rows.append({
                    'name': name,
                    'pct': pct,
                    'change': change,
                    'is_subheader': False,
                })
            i += 1
            continue

        # Spacer columns (stats_col_left) or anything else: skip
        i += 1

    return rows


def save_to_csv(sections, filename, category_name):
    """
    Saves the monthly sections to a CSV file.
    Format: category|may|jun|jul|aug|sep|change
    """
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        # Use pipe as separator
        writer = csv.writer(csvfile, delimiter='|')

        # CSV header
        header = [category_name] + [m.lower() for m in MONTHS] + ['change']
        writer.writerow(header)

        # Write each section as a subtitle plus its data
        for section in sections:
            # Write section name as subtitle
            if section['name']:
                writer.writerow([f"=== {section['name']} ==="] + [''] * len(MONTHS) + [''])

            # Write data rows
            for row in section['rows']:
                row_data = [row['name']] + row['months'] + [row['change']]
                writer.writerow(row_data)

    print(f"  Saved: {filename} ({sum(len(s['rows']) for s in sections)} rows)")


def save_main_category_to_csv(rows, filename, category_name):
    """
    Saves one main-page category (no month history, only pct + change).
    Format: category|pct|change
    Subgroup headers (Windows/OSX/Linux) are saved as === NAME === rows.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter='|')
        writer.writerow([category_name, 'pct', 'change'])
        for row in rows:
            if row.get('is_subheader'):
                writer.writerow([f"=== {row['name']} ===", '', ''])
            else:
                writer.writerow([row['name'], row['pct'], row['change']])

    print(f"  Saved: {filename} ({len(rows)} rows)")


def main():
    """Main scraper function."""
    print("=" * 60)
    print("Steam Hardware Survey Scraper")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Create output directory if it does not exist
    output_dir = 'data'
    os.makedirs(output_dir, exist_ok=True)

    # 1) Monthly history subpages
    for subpage, csv_filename in SUBPAGES.items():
        url = f"{BASE_URL}/{subpage}/"
        print(f"\nProcessing: {subpage}")
        print(f"  URL: {url}")

        # Download page
        soup = fetch_page(url)
        if not soup:
            continue

        # Extract data
        sections = extract_table_data(soup)
        if not sections:
            print("  No data extracted")
            continue

        # Save to CSV
        output_path = os.path.join(output_dir, csv_filename)
        save_to_csv(sections, output_path, category_name=subpage)

        # Pause to avoid overloading the server
        time.sleep(1)

    # 2) Main page (/) bottom table, split into several CSVs
    main_url = f"{BASE_URL}/"
    print(f"\nProcessing: main page (bottom table only)")
    print(f"  URL: {main_url}")
    soup = fetch_page(main_url)
    if soup:
        main_stats = extract_main_stats(soup)
        if not main_stats:
            print("  No main table data extracted")
        for details_id, (csv_filename, slug, fallback_label) in MAIN_PAGE_SPLIT.items():
            entry = main_stats.get(details_id)
            if not entry:
                print(f"  Skipping {details_id}: not found on page")
                continue
            label = entry.get('label') or fallback_label
            print(f"  Category: {label} -> {csv_filename} ({len(entry['rows'])} rows)")
            output_path = os.path.join(output_dir, csv_filename)
            save_main_category_to_csv(entry['rows'], output_path, category_name=slug)
        time.sleep(1)

    print()
    print("=" * 60)
    print("Extraction completed!")
    print(f"Files saved in: {output_dir}/")
    print("=" * 60)


if __name__ == '__main__':
    main()
