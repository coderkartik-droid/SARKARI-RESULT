"""Run Django test suite and print results to a file."""
import os, subprocess, sys
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.development"
result = subprocess.run(
    [sys.executable, "manage.py", "test", "--verbosity=2"],
    capture_output=True, text=True,
    cwd=os.path.dirname(os.path.abspath(__file__))
)
output = result.stdout + "\n" + result.stderr
with open("test_capture.txt", "w", encoding="utf-8") as f:
    f.write(output)
print(f"Exit code: {result.returncode}")
print("Last 40 lines:")
for line in output.splitlines()[-40:]:
    print(line)
