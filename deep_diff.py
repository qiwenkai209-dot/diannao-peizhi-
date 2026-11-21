import subprocess

def run(cmd):
    p = subprocess.run(cmd, cwd=r"C:\Users\mac\Desktop\diannao-peizhi-", shell=True, capture_output=True, text=True)
    return p.stdout

files_changed = run("git diff --name-only dc216d5 HEAD").splitlines()
print("Files changed since dc216d5:")
for f in files_changed:
    print(" -", f)
    diff_text = run(f"git diff dc216d5 HEAD -- {f}")
    print(f"--- DIFF FOR {f} ---")
    print(diff_text[:3000])
    print("=" * 60)

