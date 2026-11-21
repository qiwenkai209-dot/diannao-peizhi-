import os
import re

lib_dir = r"C:\Users\mac\Desktop\diannao-peizhi-\gwc_master_android\lib"
err_count = 0
for root, dirs, files in os.walk(lib_dir):
    for f in files:
        if f.endswith(".dart"):
            file_path = os.path.join(root, f)
            with open(file_path, "r", encoding="utf-8") as fl:
                for line in fl:
                    line = line.strip()
                    if line.startswith("import "):
                        match = re.search(r"['\"]([^'\"]+)['\"]", line)
                        if match:
                            imp = match.group(1)
                            if not imp.startswith("package:") and not imp.startswith("dart:"):
                                target = os.path.normpath(os.path.join(root, imp))
                                if not os.path.exists(target):
                                    print(f"[-] ERROR in {f}: missing file '{imp}' -> '{target}'")
                                    err_count += 1
                            elif imp.startswith("package:"):
                                print(f"[pkg] {f}: {imp}")

print(f"Total missing relative imports: {err_count}")

