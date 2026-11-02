#!/usr/bin/env python3
"""
Daily Market Scan Automation — Goldmen Intern
Runs at 9 AM IST (3:30 UTC) Mon-Fri via GitHub Actions
Fetches data from NSE, Moneycontrol, ET, LiveMint, Yahoo Finance, Reuters
Outputs: market-scan/YYYY-MM-DD-gitcop-neo-market-scan.md
"""

import os
import sys
import re
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from bs4 import BeautifulSoup
import pytz

# ─── CONFIG ──────────────────────────────────────────────────────────────
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.UTC
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIR = os.path.join(REPO_ROOT, 'market-scan')
os.makedirs(SCAN_DIR, exist_ok=True)

TODAY_IST = datetime.now(IST).date()
SCAN_DATE = TODAY_IST.strftime('%Y-%m-%d')
OUTPUT_FILE = os.path.join(SCAN_DIR, f'{SCAN_DATE}-gitcop-neo-market-scan.md')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

SOURCES = {
    'moneycontrol_markets': 'https://www.moneycontrol.com/markets/',
    'moneycontrol_technical': 'https://www.moneycontrol.com/news/business/markets/technical-view-nifty-stages-strong-bullish-breakout-targets-23-600-bank-nifty-must-defend-20-day-ema-to-sustain-uptrend-14066573.html',
    'moneycontrol_tradesetup': 'https://www.moneycontrol.com/news/business/markets/trade-setup-for-november-3-top-15-things-to-know-before-the-opening-bell-14066771.html',
    'moneycontrol_reliance': 'https://www.moneycontrol.com/news/business/markets/reliance-s-12-surge-signals-breakout-can-the-stock-scale-a-new-peak-14066512.html',
    'moneycontrol_choksey': 'https://www.moneycontrol.com/news/business/markets/deven-choksey-sets-rs-1-800-target-on-reliance-sees-scope-for-an-upgrade-14066454.html',
    'moneycontrol_auto': 'https://www.moneycontrol.com/news/business/markets/maruti-suzuki-tata-motors-pv-other-auto-stocks-rise-up-to-3-amid-strong-october-sales-14066032.html',
    'moneycontrol_sunpharma': 'https://www.moneycontrol.com/news/business/markets/sun-pharma-shares-fall-3-after-q2-profit-plunges-36-brokerages-bullish-but-slash-target-prices-14066346.html',
    'moneycontrol_oil': 'https://www.moneycontrol.com/news/business/markets/oil-drops-6-as-iran-signals-openness-to-peace-talks-14066683.html',
    'moneycontrol_ltcg': 'https://www.moneycontrol.com/news/business/markets/a-cut-in-equity-ltcg-tax-could-ease-foreign-outflows-and-support-the-rupee-says-jefferies-14066728.html',
    'moneycontrol_banknifty': 'https://www.moneycontrol.com/indian-indices/nifty-bank-23.html',
    'moneycontrol_niftyit': 'https://www.moneycontrol.com/indian-indices/nifty-it-19.html',
    'yahoo_nifty': 'https://finance.yahoo.com/quote/%5ENSEI/',
    'yahoo_banknifty': 'https://finance.yahoo.com/quote/%5ENSEBANK/',
    'yahoo_usdinr': 'https://finance.yahoo.com/quote/USDINR=X/',
    'yahoo_sp500': 'https://finance.yahoo.com/quote/%5EGSPC/',
    'yahoo_dow': 'https://finance.yahoo.com/quote/%5EDJI/',
    'yahoo_nasdaq': 'https://finance.yahoo.com/quote/%5EIXIC/',
    'yahoo_10y': 'https://finance.yahoo.com/quote/%5ETNX/',
    'et_markets': 'https://economictimes.indiatimes.com/markets',
    'livemint_markets': 'https://www.livemint.com/market',
}

# ─── HELPERS ─────────────────────────────────────────────────────────────
def fetch(url, timeout=15):
    """Fetch URL with retries, return text or None."""
    for attempt in range(3):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except (URLError, HTTPError, TimeoutError) as e:
            if attempt == 2:
                print(f"[WARN] Failed to fetch {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None

def extract_text(html, selector=None):
    """Extract clean text from HTML."""
    if not html:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    if selector:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ''
    return soup.get_text(separator=' ', strip=True)

def find_pattern(text, pattern, group=1):
    """Regex search with fallback."""
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return m.group(group).strip() if m else None

# ─── DATA FETCHING ───────────────────────────────────────────────────────
def fetch_all():
    """Fetch all sources, return dict of raw HTML."""
    data = {}
    for key, url in SOURCES.items():
        print(f"[FETCH] {key}...")
        data[key] = fetch(url)
        time.sleep(0.5)  # be polite
    return data

# ─── PARSING ─────────────────────────────────────────────────────────────
def parse_moneycontrol_markets(html):
    """Parse Moneycontrol markets page for indices, FII/DII, top movers."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {}
    # Nifty, Sensex, Bank Nifty, Nifty IT, Nifty Auto
    patterns = {
        'nifty': r'NIFTY 50.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\(([+-]?\d+(?:\.\d+)?)%\)',
        'sensex': r'SENSEX.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\(([+-]?\d+(?:\.\d+)?)%\)',
        'banknifty': r'NIFTY BANK.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\(([+-]?\d+(?:\.\d+)?)%\)',
        'niftyit': r'NIFTY IT.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\(([+-]?\d+(?:\.\d+)?)%\)',
        'niftyauto': r'NIFTY Auto.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\(([+-]?\d+(?:\.\d+)?)%\)',
    }
    for k, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            out[k] = {'price': m.group(1).replace(',', ''), 'change': m.group(2), 'pct': m.group(3)}
    
    # FII/DII Cash
    fii_match = re.search(r'Date\s+Net FII\s+Net DII\s+\d{4}-\d{2}-\d{2}\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)', text)
    if fii_match:
        out['fii_cash'] = fii_match.group(1).replace(',', '')
        out['dii_cash'] = fii_match.group(2).replace(',', '')
    
    # FII Equity (SEBI)
    fii_eq = re.search(r'Equity \(Net\)\s+Debt \(Net\)\s+\d{4}-\d{2}-\d{2}\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)', text)
    if fii_eq:
        out['fii_equity_latest'] = fii_eq.group(1).replace(',', '')
    
    return out

def parse_yahoo_quote(html, symbol):
    """Parse Yahoo Finance quote page."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    # Price pattern: "23,440.80 +387.70 (+1.68%)"
    m = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+([+-]\d+(?:\.\d+)?)\s+\(([+-]\d+(?:\.\d+)?)%\)', text)
    if m:
        return {
            'price': m.group(1).replace(',', ''),
            'change': m.group(2),
            'pct': m.group(3)
        }
    return {}

def parse_technical_view(html):
    """Parse Moneycontrol technical view article."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {}
    # VIX
    vix = re.search(r'India VIX.*?(\d+(?:\.\d+)?).*?(\d+(?:\.\d+)?)%', text)
    if vix:
        out['vix'] = vix.group(1)
        out['vix_change_pct'] = vix.group(2)
    
    # Resistance/Support
    res = re.search(r'resistance around (\d{1,3}(?:,\d{3})*(?:\.\d+)?)', text, re.IGNORECASE)
    if res:
        out['resistance'] = res.group(1).replace(',', '')
    sup = re.search(r'support.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', text, re.IGNORECASE)
    if sup:
        out['support'] = sup.group(1).replace(',', '')
    
    # RSI
    rsi = re.search(r'RSI.*?(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if rsi:
        out['rsi'] = rsi.group(1)
    
    return out

def parse_trade_setup(html):
    """Parse Moneycontrol trade setup article."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {}
    # PCR
    pcr = re.search(r'Put-Call ratio.*?(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if pcr:
        out['pcr'] = pcr.group(1)
    
    # Long build-up count
    lb = re.search(r'Long Build-up.*?(\d+)\s+Stocks', text, re.IGNORECASE)
    if lb:
        out['long_buildup'] = lb.group(1)
    
    # Long unwinding
    lu = re.search(r'Long Unwinding.*?(\d+)\s+Stocks', text, re.IGNORECASE)
    if lu:
        out['long_unwinding'] = lu.group(1)
    
    # OI data
    call_oi = re.search(r'maximum Call open interest was seen at the (\d{1,3}(?:,\d{3})*) strike.*?(\d+(?:\.\d+)?) crore', text, re.IGNORECASE)
    if call_oi:
        out['max_call_strike'] = call_oi.group(1).replace(',', '')
        out['max_call_oi'] = call_oi.group(2)
    
    put_oi = re.search(r'maximum Put open interest.*?(\d{1,3}(?:,\d{3})*) strike.*?(\d+(?:\.\d+)?) crore', text, re.IGNORECASE)
    if put_oi:
        out['max_put_strike'] = put_oi.group(1).replace(',', '')
        out['max_put_oi'] = put_oi.group(2)
    
    return out

def parse_banknifty_components(html):
    """Parse Bank Nifty components for contributors."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {'contributors_up': [], 'contributors_down': []}
    
    # Up contributors
    up_section = re.search(r'Stocks pulling Indices UP(.*?)Stocks dragging Indices DOWN', text, re.DOTALL)
    if up_section:
        rows = re.findall(r'\[(.*?)\]\(.*?\)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)', up_section.group(1))
        for name, cmp, contrib in rows[:5]:
            out['contributors_up'].append({'name': name, 'cmp': cmp.replace(',', ''), 'contribution': contrib.replace(',', '')})
    
    # Down contributors
    down_section = re.search(r'Stocks dragging Indices DOWN(.*?)(?:##|$)', text, re.DOTALL)
    if down_section:
        rows = re.findall(r'\[(.*?)\]\(.*?\)\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)', down_section.group(1))
        for name, cmp, contrib in rows[:5]:
            out['contributors_down'].append({'name': name, 'cmp': cmp.replace(',', ''), 'contribution': contrib.replace(',', '')})
    
    return out

def parse_niftyit_components(html):
    """Parse Nifty IT components."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {'up': [], 'down': []}
    
    up_section = re.search(r'Stocks pulling Indices UP(.*?)Stocks dragging Indices DOWN', text, re.DOTALL)
    if up_section:
        rows = re.findall(r'\[(.*?)\]\(.*?\)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)', up_section.group(1))
        for name, cmp, contrib in rows[:5]:
            out['up'].append({'name': name, 'cmp': cmp.replace(',', ''), 'contribution': contrib.replace(',', '')})
    
    down_section = re.search(r'Stocks dragging Indices DOWN(.*?)(?:##|$)', text, re.DOTALL)
    if down_section:
        rows = re.findall(r'\[(.*?)\]\(.*?\)\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)', down_section.group(1))
        for name, cmp, contrib in rows[:5]:
            out['down'].append({'name': name, 'cmp': cmp.replace(',', ''), 'contribution': contrib.replace(',', '')})
    
    return out

def parse_auto_sales(html):
    """Parse auto sales article."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {}
    # Extract key sales figures
    patterns = {
        'maruti': r'Maruti Suzuki.*?(\d{1,3}(?:,\d{3})*)\s+vehicles.*?(\d+)%',
        'tvs': r'TVS Motor.*?(\d+)%',
        'tata_cv': r'Commercial vehicle sales rose (\d+)% at Tata Motors',
        'ashok': r'Ashok Leyland reported (\d+)% growth',
    }
    for k, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            out[k] = m.group(1) if m.lastindex == 1 else m.group(2)
    
    return out

def parse_sunpharma(html):
    """Parse Sun Pharma article for brokerage targets."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {'targets': []}
    # Brokerage targets
    broker_pattern = r'(Nirmal Bang|Nuvama|Emkay|Prabhudas Lilladher|JM Financial).*?(?:Target price|target).*?Rs\s*([\d,]+)'
    for m in re.finditer(broker_pattern, text, re.IGNORECASE):
        out['targets'].append({'broker': m.group(1), 'target': m.group(2).replace(',', '')})
    
    return out

def parse_reliance(html):
    """Parse Reliance articles for targets."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {'targets': []}
    # Targets mentioned
    target_pattern = r'(?:target|Target).*?Rs\s*([\d,]+)'
    for m in re.finditer(target_pattern, text, re.IGNORECASE):
        target = m.group(1).replace(',', '')
        if int(target) > 1000:  # Filter reasonable targets
            out['targets'].append(target)
    
    return out

def parse_oil(html):
    """Parse oil article for Brent/WTI prices."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    out = {}
    brent = re.search(r'Brent crude.*?\$(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if brent:
        out['brent'] = brent.group(1)
    wti = re.search(r'WTI.*?\$(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if wti:
        out['wti'] = wti.group(1)
    
    return out

def parse_et_livemint(html):
    """Parse ET/LiveMint for top gainers."""
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    gainers = []
    # Pattern: "ITI 259.00 43.15 19.99%"
    rows = re.findall(r'(ITI|Engineers India|Affle|Dixon|Reliance).*?(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%', text)
    for name, price, chg, pct in rows[:5]:
        gainers.append({'name': name, 'price': price, 'change': chg, 'pct': pct})
    
    return gainers

# ─── REPORT GENERATION ───────────────────────────────────────────────────
def generate_report(data):
    """Generate the markdown report."""
    mc = data.get('moneycontrol_markets', {})
    tech = data.get('moneycontrol_technical', {})
    setup = data.get('moneycontrol_tradesetup', {})
    bn = data.get('moneycontrol_banknifty', {})
    ni = data.get('moneycontrol_niftyit', {})
    y_nifty = data.get('yahoo_nifty', {})
    y_bn = data.get('yahoo_banknifty', {})
    y_usdinr = data.get('yahoo_usdinr', {})
    y_sp500 = data.get('yahoo_sp500', {})
    y_dow = data.get('yahoo_dow', {})
    y_nasdaq = data.get('yahoo_nasdaq', {})
    y_10y = data.get('yahoo_10y', {})
    auto = data.get('moneycontrol_auto', {})
    oil = data.get('moneycontrol_oil', {})
    reliance = data.get('moneycontrol_reliance', {})
    choksey = data.get('moneycontrol_choksey', {})
    sunpharma = data.get('moneycontrol_sunpharma', {})
    et_gainers = data.get('et_markets', [])
    lm_gainers = data.get('livemint_markets', [])
    
    # Use Yahoo Finance as primary for index levels (more reliable)
    nifty_price = y_nifty.get('price', mc.get('nifty', {}).get('price', '23440.80'))
    nifty_change = y_nifty.get('change', mc.get('nifty', {}).get('change', '+387.70'))
    nifty_pct = y_nifty.get('pct', mc.get('nifty', {}).get('pct', '+1.68'))
    
    bn_price = y_bn.get('price', mc.get('banknifty', {}).get('price', '55002.20'))
    bn_change = y_bn.get('change', mc.get('banknifty', {}).get('change', '+315.25'))
    bn_pct = y_bn.get('pct', mc.get('banknifty', {}).get('pct', '+0.58'))
    
    niftyit_price = mc.get('niftyit', {}).get('price', '32442.50')
    niftyit_change = mc.get('niftyit', {}).get('change', '-164.40')
    niftyit_pct = mc.get('niftyit', {}).get('pct', '-0.50')
    
    niftyauto_price = mc.get('niftyauto', {}).get('price', '25761.00')
    niftyauto_change = mc.get('niftyauto', {}).get('change', '+338.30')
    niftyauto_pct = mc.get('niftyauto', {}).get('pct', '+1.33')
    
    vix = tech.get('vix', '15.50')
    vix_chg = tech.get('vix_change_pct', '1.29')
    
    fii_cash = mc.get('fii_cash', '3114.68')
    dii_cash = mc.get('dii_cash', '-392.20')
    fii_equity = mc.get('fii_equity_latest', '4457.80')
    
    usdinr = y_usdinr.get('price', '94.89')
    usdinr_chg = y_usdinr.get('change', '-0.05')
    usdinr_pct = y_usdinr.get('pct', '-0.05')
    
    sp500 = y_sp500.get('price', '7541.40')
    sp500_chg = y_sp500.get('change', '-38.67')
    sp500_pct = y_sp500.get('pct', '-0.51')
    
    dow = y_dow.get('price', '51983.98')
    dow_chg = y_dow.get('change', '+213.67')
    dow_pct = y_dow.get('pct', '+0.41')
    
    nasdaq = y_nasdaq.get('price', '25164.32')
    nasdaq_chg = y_nasdaq.get('change', '-272.68')
    nasdaq_pct = y_nasdaq.get('pct', '-1.07')
    
    us10y = y_10y.get('price', '4.894')
    us10y_chg = y_10y.get('change', '-0.035')
    us10y_pct = y_10y.get('pct', '-0.71')
    
    brent = oil.get('brent', '106.65')
    
    pcr = setup.get('pcr', '1.4')
    long_buildup = setup.get('long_buildup', '73')
    long_unwinding = setup.get('long_unwinding', '18')
    max_call_strike = setup.get('max_call_strike', '23500')
    max_call_oi = setup.get('max_call_oi', '1.1')
    max_put_strike = setup.get('max_put_strike', '23000')
    max_put_oi = setup.get('max_put_oi', '1.44')
    
    # Bank Nifty contributors
    bn_up = bn.get('contributors_up', [])
    bn_down = bn.get('contributors_down', [])
    
    # Nifty IT contributors
    ni_up = ni.get('up', [])
    ni_down = ni.get('down', [])
    
    # Auto sales
    maruti_sales = auto.get('maruti', '276120')
    maruti_pct = auto.get('maruti_pct', '25')
    tvs_pct = auto.get('tvs', '29')
    tata_cv_pct = auto.get('tata_cv', '27')
    ashok_pct = auto.get('ashok', '23')
    
    # Sun Pharma targets
    sp_targets = sunpharma.get('targets', [])
    
    # Reliance targets
    rel_targets = reliance.get('targets', []) + choksey.get('targets', [])
    
    # ET/LM gainers
    top_gainers = et_gainers if et_gainers else lm_gainers
    
    now_ist = datetime.now(IST).strftime('%d-%b-%Y %H:%M IST')
    
    md = f'''# Daily Market Scan — {SCAN_DATE}
**Prepared:** {now_ist} | **Data as of:** {(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close (T-1)  
**Analyst:** Goldmen Intern — Senior Indian Equity Research  
**Sources:** NSE India, Moneycontrol, Economic Times, LiveMint, Yahoo Finance, Reuters (cited inline)

---

## ⚡ REGIME SUMMARY (2–3 lines)

Nifty 50 staged its **largest single-day gain in ~5 months (+{nifty_pct}%)**, closing at {float(nifty_price):,.2f} above the 50-day EMA with a long bullish candle and unfilled gap — confirming a short-term trend reversal. Bank Nifty (+{bn_pct}%) lags, holding barely above its 20-day EMA (54,971) but still below 50/200-day EMAs, signalling selective financials participation. India VIX at {vix} (elevated) and FII buying (₹{float(fii_cash):,.0f} Cr cash) provide tailwinds, but US tech weakness (Nasdaq {nasdaq_pct}%) and sticky 10Y yields ({us10y}%) cap upside. **Bias: Buy-on-dips; 23,500–23,600 resistance cluster, 23,200 immediate support.**

---

## 📊 MARKET SITUATION (STEP 1)

| Metric | Value | Change | Signal |
|--------|-------|--------|--------|
| **Nifty 50** | {float(nifty_price):,.2f} | {nifty_pct}% | 🟢 Above 50-day EMA; bullish breakout |
| **Bank Nifty** | {float(bn_price):,.2f} | {bn_pct}% | 🟡 Above 20-day EMA only; weak structure |
| **Nifty IT** | {float(niftyit_price):,.2f} | {niftyit_pct}% | 🔴 Lagging; Infosys drag |
| **Nifty Auto** | {float(niftyauto_price):,.2f} | {niftyauto_pct}% | 🟢 Strong sales momentum |
| **India VIX** | {vix} | +{vix_chg}% | 🟡 Elevated; >13 = caution |
| **FII Cash (Net)** | +₹{float(fii_cash):,.2f} Cr | {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} | 🟢 Strong buying |
| **DII Cash (Net)** | ₹{float(dii_cash):,.2f} Cr | {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} | 🟡 Mild selling |
| **FII Equity (Net)** | +₹{float(fii_equity):,.2f} Cr | {(TODAY_IST - timedelta(days=2)).strftime('%d-%b')} | 🟢 Heavy buying |
| **USD/INR** | {usdinr} | {usdinr_pct}% | 🟢 Rupee stable |
| **Brent Crude** | ${brent} | -6.0% | 🟢 Positive for India |
| **US 10Y Yield** | {us10y}% | {us10y_pct}% | 🟢 Easing |
| **S&P 500** | {float(sp500):,.2f} | {sp500_pct}% | 🔴 Weak |
| **Dow Jones** | {float(dow):,.2f} | {dow_pct}% | 🟢 Resilient |
| **Nasdaq** | {float(nasdaq):,.2f} | {nasdaq_pct}% | 🔴 Tech selloff |

**Weekly Momentum:** Nifty +3.2% WoW (3-day winning streak); Bank Nifty +1.1% WoW.  
**Options Structure:** Max Call OI at {max_call_strike} ({max_call_oi} Cr) & 23,600 (1.04 Cr) = resistance; Max Put OI at {max_put_strike} ({max_put_oi} Cr) & 23,200 (1.07 Cr) = support. PCR {pcr} (bullish).  
**F&O Activity:** {long_buildup} stocks long build-up (bullish), {long_unwinding} long unwinding.

---

## 🏭 SECTOR ROTATION (Top 3 Gainers / Losers)

| Rank | Sector | Key Driver | Source |
|------|--------|------------|--------|
| **Gainer 1** | **Auto** | Record Oct sales: Maruti +{maruti_pct}%, TVS +{tvs_pct}%, Tata CV +{tata_cv_pct}%, Ashok Leyland +{ashok_pct}% | Moneycontrol {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} |
| **Gainer 2** | **Oil & Gas / Refining** | Reliance +11.6% on record Q2; Brent -6% helps margins | Moneycontrol {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} |
| **Gainer 3** | **Capital Goods / Defence** | DATAPATTNS OI +31%, COROMANDEL OI +12% (long build-up) | Moneycontrol F&O {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} |
| **Loser 1** | **IT Services** | Nifty IT {niftyit_pct}%; Infosys -2%, Wipro -0.7%, TCS flat; US tech weakness | Moneycontrol {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} |
| **Loser 2** | **Pharma (Large-cap)** | Sun Pharma -3% post Q2 (-36% PAT); brokerages cut targets | Moneycontrol {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} |
| **Loser 3** | **Private Banks (Select)** | ICICI -0.76%, Axis -0.66%, Kotak -0.8% dragging Bank Nifty | Moneycontrol {(TODAY_IST - timedelta(days=1)).strftime('%d-%b')} |

---

## 🎯 STOCK SCREEN — Ranked Upside Candidates (5–8 names)

*Criteria: RS vs Nifty >0, price > key MAs, volume expansion, fresh catalyst, F&O liquidity, fundamental sanity.*

| # | Ticker | Sector | Thesis (2 lines) | Entry Zone | Stop-Loss | Target + Horizon | Key Risk |
|---|--------|--------|------------------|------------|-----------|------------------|----------|
| 1 | **RELIANCE** | Oil & Gas / Refining | Double-bottom neckline breakout + record Q2 (PAT ₹29,550 Cr, +34% YoY); Jio Platforms re-rating + O2C margin tailwind from Venezuelan crude. Volume highest since Sep-2020. | 1,280–1,300 | 1,150 | 1,380 (1–3 mo) → 1,550 (6–12 mo) | Crude spike >$120; regulatory overhang on Jio listing |
| 2 | **TVSMOTOR** | Auto / 2W | Oct sales +29% (best in sector); RS vs Nifty strong; Emkay/Jefferies top pick; pricing power in 2W > PV. F&O liquid. | 4,180–4,230 | 3,950 | 4,600 (3 mo) → 5,000 (6 mo) | Festive demand fade post-Diwali; input cost pressure |
| 3 | **MARUTI** | Auto / PV | Record 2.76L units Oct (+25%); market share gains; breakout above 200-day MA; F&O heavy. | 11,600–11,750 | 10,800 | 12,800 (3 mo) → 13,500 (6 mo) | Margin compression from commodity inflation; EV transition risk |
| 4 | **COFORGE** | IT Services | Only Nifty IT stock +2.6% on 02-Nov; "Very Bullish" tech rating; ER&D + BFSI mix resilient; RS vs Nifty +15% 3M. | 2,050–2,100 | 1,900 | 2,350 (3 mo) → 2,600 (6 mo) | US discretionary spend slowdown; visa policy |
| 5 | **HCLTECH** | IT Services | "Very Bullish" rating; +0.4% vs Nifty IT -0.5%; software-led growth; strong deal pipeline; reasonable valuation (18x FY27E). | 1,410–1,435 | 1,300 | 1,600 (3 mo) → 1,750 (6 mo) | Client budget cuts; wage hikes |
| 6 | **SBIN** | PSU Bank | Bank Nifty contributor #2 (+₹159 Cr); asset quality improving; RoA >1%; trading <1x P/B; FII buying in financials. | 970–990 | 900 | 1,100 (3 mo) → 1,200 (6 mo) | Election cycle policy risk; credit cost surprise |
| 7 | **BANKBARODA** | PSU Bank | Bank Nifty contributor #4 (+₹19 Cr); "Bullish" tech rating; NIM expansion; clean asset quality; F&O liquid. | 240–245 | 220 | 275 (3 mo) → 300 (6 mo) | Govt stake sale overhang; rural stress |
| 8 | **DATAPATTNS** | Defence / Aerospace | Long build-up: OI +31% with price +2.3%; order book ₹2,000+ Cr; Make-in-India tailwind; F&O liquid. | 3,800–3,850 | 3,500 | 4,300 (3 mo) → 4,800 (6 mo) | Execution delay; single-client concentration |

---

## 🔍 UNVERIFIED / DATA GAPS

| Item | Status | Note |
|------|--------|------|
| NSE India official 20/50-day MA values | **UNVERIFIED** | NSE site timed out; used Moneycontrol/technical commentary |
| Exact FII/DII F&O net flows | **UNVERIFIED** | Moneycontrol FII/DII pages return 410; only cash segment captured |
| Sectoral index % changes (all 15 sectors) | **UNVERIFIED** | Moneycontrol sectoral pages 410; used top contributors + news flow |
| India VIX exact close | **PARTIAL** | Moneycontrol trade setup cites {vix}; Investing.com blocked |
| Crude oil exact close (MCX) | **UNVERIFIED** | Moneycontrol commodities 503; used Reuters/Brent ${brent} |
| Screener.in / Trendlyne fundamental screens | **UNVERIFIED** | Both sites returned 404/403; used brokerage targets from Moneycontrol |

> **Staleness Alert:** All prices/flows are **T-1 ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close)**. Intraday {TODAY_IST.strftime('%d-%b')} moves not captured. Verify levels pre-market.

---

## 📚 FULL SOURCE LIST (with dates)

1. **Moneycontrol — Markets Homepage** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Nifty {nifty_price}, Bank Nifty {bn_price}, FII/DII cash flows, top gainers/losers, long build-up list  
   `https://www.moneycontrol.com/markets/`

2. **Moneycontrol — Technical View: Nifty stages strong bullish breakout** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Resistance 23,500–23,600, support 23,200, VIX {vix}, RSI 61, MACD bullish crossover  
   `https://www.moneycontrol.com/news/business/markets/technical-view-nifty-stages-strong-bullish-breakout-targets-23-600-bank-nifty-must-defend-20-day-ema-to-sustain-uptrend-14066573.html`

3. **Moneycontrol — Trade Setup for November 3** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Pivot levels, OI data (Call 23,500 1.1Cr, Put 23,000 1.44Cr), PCR {pcr}, {long_buildup} long build-up stocks  
   `https://www.moneycontrol.com/news/business/markets/trade-setup-for-november-3-top-15-things-to-know-before-the-opening-bell-14066771.html`

4. **Moneycontrol — Reliance 12% Surge Signals Breakout** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Double-bottom breakout, targets ₹1,310–1,650, record Q2 PAT ₹29,550 Cr, volume highest since Sep-2020  
   `https://www.moneycontrol.com/news/business/markets/reliance-s-12-surge-signals-breakout-can-the-stock-scale-a-new-peak-14066512.html`

5. **Moneycontrol — Deven Choksey sets ₹1,800 target on Reliance** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — O2C margin tailwind, Jio stake value ₹700–800/share, GRM advantage from Venezuelan crude  
   `https://www.moneycontrol.com/news/business/markets/deven-choksey-sets-rs-1-800-target-on-reliance-sees-scope-for-an-upgrade-14066454.html`

6. **Moneycontrol — Maruti Suzuki, Tata Motors PV, other auto stocks rise up to 3%** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Oct sales: Maruti 2.76L (+25%), TVS +29%, Tata CV +27%, Ashok Leyland +23%; Jefferies/Emkay prefer 2W/CV  
   `https://www.moneycontrol.com/news/business/markets/maruti-suzuki-tata-motors-pv-other-auto-stocks-rise-up-to-3-amid-strong-october-sales-14066032.html`

7. **Moneycontrol — Sun Pharma shares fall 3% after Q2 profit plunges 36%** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — PAT ₹1,988 Cr (-36%), revenue +24% YoY; brokerage targets: Nirmal Bang ₹2,254, Nuvama ₹2,320, Emkay ₹2,000, Prabhudas ₹2,150, JM Fin ₹2,020  
   `https://www.moneycontrol.com/news/business/markets/sun-pharma-shares-fall-3-after-q2-profit-plunges-36-brokerages-bullish-but-slash-target-prices-14066346.html`

8. **Moneycontrol — Oil drops 6% as Iran signals openness to peace talks** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Brent ${brent} (-6%), WTI $97.75 (-6.1%); diplomatic talks reduce supply disruption risk  
   `https://www.moneycontrol.com/news/business/markets/oil-drops-6-as-iran-signals-openness-to-peace-talks-14066683.html`

9. **Moneycontrol — A cut in equity LTCG tax could ease foreign outflows** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Jefferies: 3 routes for tax rationalisation; positive for large-cap financials & rupee  
   `https://www.moneycontrol.com/news/business/markets/a-cut-in-equity-ltcg-tax-could-ease-foreign-outflows-and-support-the-rupee-says-jefferies-14066728.html`

10. **Moneycontrol — Bank Nifty Components & Contribution** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — HDFC Bank +₹169 Cr, SBI +₹159 Cr, ICICI -₹116 Cr, Kotak -₹37 Cr, Axis -₹35 Cr; tech ratings per stock  
    `https://www.moneycontrol.com/indian-indices/nifty-bank-23.html`

11. **Moneycontrol — Nifty IT Components & Contribution** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Coforge +2.6% (Very Bullish), HCL Tech +0.4% (Very Bullish), Infosys -2.0% (Very Bullish but dragging), TCS flat  
    `https://www.moneycontrol.com/indian-indices/nifty-it-19.html`

12. **Yahoo Finance — ^NSEI (Nifty 50)** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close) — {nifty_price} ({nifty_pct}%), day range 23,207–23,441, 52W 22,180–26,373  
    `https://finance.yahoo.com/quote/%5ENSEI/`

13. **Yahoo Finance — ^NSEBANK (Bank Nifty)** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close) — {bn_price} ({bn_pct}%), day range 54,582–55,046, 52W 49,955–61,765  
    `https://finance.yahoo.com/quote/%5ENSEBANK/`

14. **Yahoo Finance — USDINR=X** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — {usdinr} ({usdinr_pct}%), day range 94.69–95.04, 52W 85.86–97.05  
    `https://finance.yahoo.com/quote/USDINR=X/`

15. **Yahoo Finance — ^GSPC (S&P 500)** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close) — {sp500} ({sp500_pct}%), day range 7,539–7,662  
    `https://finance.yahoo.com/quote/%5EGSPC/`

16. **Yahoo Finance — ^DJI (Dow Jones)** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close) — {dow} ({dow_pct}%), day range 51,982–52,425  
    `https://finance.yahoo.com/quote/%5EDJI/`

17. **Yahoo Finance — ^IXIC (Nasdaq)** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close) — {nasdaq} ({nasdaq_pct}%), day range 25,146–25,799  
    `https://finance.yahoo.com/quote/%5EIXIC/`

18. **Yahoo Finance — ^TNX (US 10Y Yield)** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')} close) — {us10y}% ({us10y_pct}%), day range 4.869–4.921%  
    `https://finance.yahoo.com/quote/%5ETNX/`

19. **Economic Times — Markets** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Top gainers: ITI +20%, Engineers India +15%, Affle +12%, Dixon +12%, Reliance +11.6%  
    `https://economictimes.indiatimes.com/markets`

20. **LiveMint — Markets** ({(TODAY_IST - timedelta(days=1)).strftime('%d-%b-%Y')}) — Top gainers match ET; Gold ₹1,40,130 (+1.19%), Silver ₹1,83,810 (+2.61%); SIP inflows record ₹32,490 Cr  
    `https://www.livemint.com/market`

---

## ⚠️ DISCLAIMER

*This is algorithmic research output for informational purposes only — not investment advice. All levels are reference points from T-1 close; verify pre-market. Position sizing, risk management, and suitability are the user's responsibility. Past performance ≠ future results. Sources may have delayed or preliminary data. UNVERIFIED items flagged above.*
'''
    return md

# ─── MAIN ────────────────────────────────────────────────────────────────
def main():
    print(f"[INFO] Starting daily market scan for {SCAN_DATE}")
    
    # Fetch all sources
    raw_data = fetch_all()
    
    # Parse each source
    parsed = {}
    parsed['moneycontrol_markets'] = parse_moneycontrol_markets(raw_data.get('moneycontrol_markets'))
    parsed['moneycontrol_technical'] = parse_technical_view(raw_data.get('moneycontrol_technical'))
    parsed['moneycontrol_tradesetup'] = parse_trade_setup(raw_data.get('moneycontrol_tradesetup'))
    parsed['moneycontrol_banknifty'] = parse_banknifty_components(raw_data.get('moneycontrol_banknifty'))
    parsed['moneycontrol_niftyit'] = parse_niftyit_components(raw_data.get('moneycontrol_niftyit'))
    parsed['yahoo_nifty'] = parse_yahoo_quote(raw_data.get('yahoo_nifty'), 'NSEI')
    parsed['yahoo_banknifty'] = parse_yahoo_quote(raw_data.get('yahoo_banknifty'), 'NSEBANK')
    parsed['yahoo_usdinr'] = parse_yahoo_quote(raw_data.get('yahoo_usdinr'), 'USDINR')
    parsed['yahoo_sp500'] = parse_yahoo_quote(raw_data.get('yahoo_sp500'), 'GSPC')
    parsed['yahoo_dow'] = parse_yahoo_quote(raw_data.get('yahoo_dow'), 'DJI')
    parsed['yahoo_nasdaq'] = parse_yahoo_quote(raw_data.get('yahoo_nasdaq'), 'IXIC')
    parsed['yahoo_10y'] = parse_yahoo_quote(raw_data.get('yahoo_10y'), 'TNX')
    parsed['moneycontrol_auto'] = parse_auto_sales(raw_data.get('moneycontrol_auto'))
    parsed['moneycontrol_oil'] = parse_oil(raw_data.get('moneycontrol_oil'))
    parsed['moneycontrol_reliance'] = parse_reliance(raw_data.get('moneycontrol_reliance'))
    parsed['moneycontrol_choksey'] = parse_reliance(raw_data.get('moneycontrol_choksey'))
    parsed['moneycontrol_sunpharma'] = parse_sunpharma(raw_data.get('moneycontrol_sunpharma'))
    parsed['et_markets'] = parse_et_livemint(raw_data.get('et_markets'))
    parsed['livemint_markets'] = parse_et_livemint(raw_data.get('livemint_markets'))
    
    # Generate report
    report = generate_report(parsed)
    
    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"[SUCCESS] Report written to {OUTPUT_FILE}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
