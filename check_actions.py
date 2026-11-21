import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs?per_page=5'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        runs = data.get('workflow_runs', [])
        for r in runs:
            print(f"ID: {r['id']}, Name: {r['name']}, Status: {r['status']}, Conclusion: {r['conclusion']}, Head: {r['head_sha'][:7]}")
            print(f"Commit: {r['head_commit']['message'].splitlines()[0]}")
except Exception as e:
    print('Error:', e)

