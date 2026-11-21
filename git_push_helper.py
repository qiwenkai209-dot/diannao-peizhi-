import subprocess
import time
import os

cwd = r"C:\Users\mac\Desktop\diannao-peizhi-"

def run_cmd(args):
    print(f"Running: {' '.join(args) if isinstance(args, list) else args}")
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=isinstance(args, str))
    if p.stdout:
        print(p.stdout.strip())
    if p.stderr:
        print("STDERR:", p.stderr.strip())
    return p.returncode

run_cmd(["git", "add", ".github/workflows/build-android.yml", "gwc_master_android/"])
commit_msg = "fix: resolve apk signature conflict with new app id, remove top batch controls, enhance single-machine control with udp 9887 and live echo"
run_cmd(["git", "commit", "-m", commit_msg])

for attempt in range(1, 6):
    print(f"--- Git push attempt {attempt}/5 ---")
    ret = run_cmd(["git", "push", "origin", "main"])
    if ret == 0:
        print("[+] Successfully pushed to GitHub main!")
        break
    time.sleep(3)

