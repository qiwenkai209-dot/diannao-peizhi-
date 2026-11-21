import os
import re

lib_dir = r"C:\Users\mac\Desktop\diannao-peizhi-\gwc_master_android\lib"

# 1. 收集所有定义的 Widget 类名及其构造参数
classes = {}
for root, dirs, files in os.walk(lib_dir):
    for f in files:
        if f.endswith(".dart"):
            with open(os.path.join(root, f), "r", encoding="utf-8") as fl:
                code = fl.read()
            # 匹配 class Xxx extends
            for cls_m in re.finditer(r"class\s+([A-Za-z0-9_]+)\s+extends\s+", code):
                cname = cls_m.group(1)
                # 寻找构造函数 const Cname({ ... })
                ctor_m = re.search(r"const\s+" + cname + r"\s*\(\s*\{([^}]*)\}\s*\)", code)
                if not ctor_m:
                    ctor_m = re.search(cname + r"\s*\(\s*\{([^}]*)\}\s*\)", code)
                required_args = []
                if ctor_m:
                    params = ctor_m.group(1)
                    for p in params.split(","):
                        p = p.strip()
                        if p.startswith("required "):
                            arg_name = p.split()[-1].replace("this.", "")
                            required_args.append(arg_name)
                classes[cname] = (f, required_args)

print("Found classes:", len(classes))
for c, (f, req) in classes.items():
    if req:
        print(f"  {c} (in {f}) requires: {req}")

# 2. 检查所有文件中的实例化是否传了 required 参数
for root, dirs, files in os.walk(lib_dir):
    for f in files:
        if f.endswith(".dart"):
            with open(os.path.join(root, f), "r", encoding="utf-8") as fl:
                code = fl.read()
            for c, (_, req) in classes.items():
                if req:
                    # 查找 cname(...)
                    for inst in re.finditer(r"\b" + c + r"\s*\(([^)]*)\)", code):
                        # 如果不是构造函数定义本身
                        inst_params = inst.group(1)
                        if "super.key" not in inst_params:
                            for r in req:
                                if f"{r}:" not in inst_params:
                                    print(f"❌ BUG FOUND in {f}: {c}(...) missing required parameter '{r}'!")
