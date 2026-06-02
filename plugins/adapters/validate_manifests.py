import json, pathlib, sys

root = pathlib.Path("registry")
files = list(root.rglob("manifest.json"))
errors = []

for f in files:
    try:
        json.loads(f.read_text(encoding="utf-8"))
        print(f"OK  {f}")
    except Exception as e:
        print(f"ERR {f}: {e}")
        errors.append(f)

print(f"\n--- {len(files) - len(errors)} OK, {len(errors)} errors ---")
sys.exit(len(errors))
