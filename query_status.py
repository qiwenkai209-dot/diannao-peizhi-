import subprocess
import json

def get(url):
    for attempt in range(1, 4):
        try:
            cmd = f'curl.exe -s -L --connect-timeout 6 --max-time 10 "{url}"'
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if p.stdout.strip().startswith('{') or p.stdout.strip().startswith('['):
                return json.loads(p.stdout)
        except Exception as e:
            pass
    return None

data = get("https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs/44858182551")
if data:
    print(f"Status: {data.get('status')}, Conclusion: {data.get('conclusion')}")

jobs_data = get("https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs/44858182551/jobs")
if jobs_data:
    for j in jobs_data.get('jobs', []):
        print(f"Job: {j.get('name')} -> {j.get('status')} ({j.get('conclusion')})")
        for s in j.get('steps', []):
            print(f"  Step: {s.get('name')} -> {s.get('status')} ({s.get('conclusion')})")

