import urllib.request
import json
import time

def fetch(url):
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except Exception as e:
            print(f"Retry {i+1} for {url}: {e}")
            time.sleep(2)
    return None

jobs_raw = fetch('https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs/44854731792/jobs')
if not jobs_raw:
    print("Failed to get jobs")
    exit(1)

data = json.loads(jobs_raw.decode())
job_id = data['jobs'][0]['id']
print("Job ID:", job_id)

logs_raw = fetch(f'https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/jobs/{job_id}/logs')
if logs_raw:
    lines = logs_raw.decode(errors='ignore').splitlines()
    # Print the last 80 lines
    print("--- LAST 80 LINES OF LOG ---")
    for l in lines[-80:]:
        print(l)
else:
    print("Failed to fetch logs")

