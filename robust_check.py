import urllib.request
import json
import ssl
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs?per_page=5'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

for i in range(10):
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            runs = data.get('workflow_runs', [])
            for r in runs:
                print(f"ID: {r['id']}, Name: {r['name']}, Status: {r['status']}, Conclusion: {r['conclusion']}, Head: {r['head_sha'][:7]}")
            break
    except Exception as e:
        print(f"Attempt {i+1} failed: {e}")
        time.sleep(2)

