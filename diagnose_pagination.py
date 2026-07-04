import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

r = httpx.get("https://redlib.perennialte.ch/user/spez/submitted", headers=HEADERS, timeout=15, follow_redirects=True)
soup = BeautifulSoup(r.text, "html.parser")

print(f"Total .post elements on page 1: {len(soup.select('.post'))}")
print()

# Check every possible pagination pattern
print("=== ALL <a> tags containing 'after' ===")
for a in soup.find_all("a", href=True):
    if "after" in a.get("href", ""):
        print(f"  text={a.text.strip()!r:20s}  href={a['href']}")

print()
print("=== ALL <a> tags with rel attribute ===")
for a in soup.find_all("a", rel=True):
    print(f"  rel={a.get('rel')}  text={a.text.strip()!r:20s}  href={a.get('href','')}")

print()
print("=== Elements with id/class containing 'next','page','nav' ===")
for el in soup.find_all(True):
    eid = el.get("id", "")
    ecls = " ".join(el.get("class", []))
    if any(k in (eid + ecls).lower() for k in ["next", "prev", "page", "nav", "more"]):
        print(f"  <{el.name} id={eid!r} class={ecls!r}>  text={el.text.strip()[:60]!r}")

print()
print("=== Last 500 chars of HTML (footer area) ===")
print(r.text[-500:])
