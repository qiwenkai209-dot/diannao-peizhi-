import subprocess
import json
import sys

run_id = sys.argv[1] if len(sys.argv) > 1 else '44858182551'
cmd = f'curl.exe -s -L --retry 5 https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs/{run_id}/jobs'
p = subprocess.run(cmd, shell=True, capture_output=True, text=True)

try:
    data = json.loads(p.stdout)
    for j in data.get('jobs', []):
        print(f"Job: {j.get('name')}, Status: {j.get('status')}, Conclusion: {j.get('conclusion')}")
        for s in j.get('steps', []):
            print(f"  Step: {s.get('name')} -> {s.get('status')} ({s.get('conclusion')})")
except Exception as e:
    print("Error parsing curl output:", e)
    print("Raw output:", p.stdout[:200])
