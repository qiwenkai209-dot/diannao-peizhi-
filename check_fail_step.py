import urllib.request
import json
import ssl
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs/44858182551/jobs'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

for i in range(10):
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for j in data.get('jobs', []):
                print(f"Job: {j['name']}, Status: {j['status']}, Conclusion: {j['conclusion']}")
                for s in j.get('steps', []):
                    if s.get('conclusion') != 'success':
                        print(f"  Step: {s['name']} -> {s['status']} ({s['conclusion']})")
            break
    except Exception as e:
        print(f"Attempt {i+1} failed: {e}")
        time.sleep(2)

