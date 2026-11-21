import urllib.request
import json
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

jobs_url = "https://api.github.com/repos/qiwenkai209-dot/diannao-peizhi-/actions/runs/44860926673/jobs"
req = urllib.request.Request(jobs_url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, context=ctx) as resp:
    data = json.loads(resp.read().decode())
    job_id = data["jobs"][0]["id"]
    print("Job ID:", job_id)

page_url = f"https://github.com/qiwenkai209-dot/diannao-peizhi-/actions/runs/44860926673/job/{job_id}"
p_req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(p_req, context=ctx) as resp:
    html = resp.read().decode("utf-8", errors="ignore")
    print("Page HTML length:", len(html))
    # 查找所有包含 logs 的链接
    urls = re.findall(r'href=["\']([^"\']*log[^"\']*)["\']', html)
    print("Log URLs:", urls)
    # 查找是否有 log-lines
    lines_m = re.findall(r'class="[^"]*log-line[^"]*"[^>]*>(.*?)</div>', html)
    print("Log lines on page:", len(lines_m))
    for l in lines_m[:20]:
        print("  ", l)

