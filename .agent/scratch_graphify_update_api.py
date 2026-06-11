import sys, json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path

# Create output dir if missing
Path('graphify-out').mkdir(exist_ok=True)

result = detect_incremental(Path('api'))
new_total = result.get('new_total', 0)
Path('graphify-out/.graphify_incremental.json').write_text(json.dumps(result))

if new_total == 0:
    print('No files changed in api/ since last run. Nothing to update.')
    sys.exit(0)

print(f'{new_total} new/changed file(s) in api/ to re-extract.')

# check if code_only
code_exts = {'.py','.ts','.js','.go','.rs','.java','.cpp','.c','.rb','.swift','.kt','.cs','.scala','.php','.cc','.cxx','.hpp','.h','.kts','.lua','.toc','.f','.F','.f90','.F90','.f95','.F95','.f03','.F03','.f08','.F08'}
new_files = result.get('new_files', {})
all_changed = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
print('code_only:', code_only)
