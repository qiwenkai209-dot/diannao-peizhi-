import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/releases'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        for rel in data[:3]:
            print(f"Tag: {rel['tag_name']}, Name: {rel['name']}, Published: {rel['published_at']}")
            for a in rel.get('assets', []):
                print(f"  Asset: {a['name']}, Size: {a['size']}, Updated: {a['updated_at']}, DownloadUrl: {a['browser_download_url']}")
except Exception as e:
    print('Error:', e)

