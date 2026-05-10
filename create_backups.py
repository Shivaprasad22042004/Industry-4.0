import shutil
import os

files_to_backup = [
    r"physics\engine.py",
    r"physics\validator.py",
    r"physics\state_machine.py",
    r"machines\config.py",
    r"simulator\tick_loop.py"
]

for file in files_to_backup:
    if os.path.exists(file):
        base, ext = os.path.splitext(file)
        backup_name = f"{base}_backup{ext}"
        shutil.copy2(file, backup_name)
        print(f"✅ Created backup: {backup_name}")
    else:
        print(f"❌ Could not find {file}")

print("\nBackup complete!")
