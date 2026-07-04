import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

r = httpx.get("https://redlib.perennialte.ch/user/spez/comments", headers=HEADERS, timeout=15, follow_redirects=True)
soup = BeautifulSoup(r.text, "html.parser")

print(f"Status: {r.status_code}")
print()

# Check what the comment items look like
for sel in [".comment", ".post", "article", ".thing"]:
    items = soup.select(sel)
    if items:
        print(f"Selector {sel!r} — {len(items)} items found")
        print("First item HTML:")
        print(items[0].prettify()[:1500])
        break

print()
# Pagination
print("=== Pagination links ===")
for a in soup.find_all("a", href=True):
    if "after" in a.get("href", "") or a.get("rel"):
        print(f"  rel={a.get('rel')}  text={a.text.strip()!r}  href={a['href']}")
