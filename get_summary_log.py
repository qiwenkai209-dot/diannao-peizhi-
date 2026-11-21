import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://github.com/qiwenkai209-dot/diannao-peizhi-/actions/runs/44860461481'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# 查找所有 markdown 渲染块或 pre/code
matches = re.findall(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL)
print("Pre blocks found:", len(matches))
for i, m in enumerate(matches):
    print(f"--- PRE BLOCK {i} ---")
    print(m[:1000])

# 查找 annotations_partial
ann_m = re.search(r'data-url="([^"]*annotations_partial[^"]*)"', html)
if ann_m:
    ann_url = "https://github.com" + ann_m.group(1)
    print("Annotations URL:", ann_url)
    req_ann = urllib.request.Request(ann_url, headers={'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'})
    with urllib.request.urlopen(req_ann, context=ctx, timeout=10) as a_resp:
        ann_html = a_resp.read().decode('utf-8', errors='ignore')
        print("Annotations HTML length:", len(ann_html))
        # 查找错误文本
        clean_text = re.sub(r'<[^>]+>', ' ', ann_html)
        print("Clean Ann Text:", ' '.join(clean_text.split())[:1500])

