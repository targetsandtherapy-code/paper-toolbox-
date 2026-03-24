"""One-off: check ECS doc_parser + journalctl business lines. Usage:
   set ECS_PASS=... && python scripts/_ssh_check_logs.py
"""
import os
import sys

try:
    import paramiko
except ImportError:
    print("pip install paramiko")
    sys.exit(1)

HOST = os.environ.get("ECS_HOST", "8.140.21.135")
USER = os.environ.get("ECS_USER", "root")
PW = os.environ.get("ECS_PASS", "")
if not PW:
    print("Set ECS_PASS environment variable to SSH password.")
    sys.exit(1)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PW, timeout=20)

def run(label: str, cmd: str) -> None:
    print("===", label, "===")
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(out.strip() or err.strip() or "(empty)")

run(
    "doc_parser _iter_body_paragraphs (first 25 lines of method)",
    "sed -n '86,115p' /root/paper-toolbox/modules/doc_parser.py",
)
run("has body.iter", "grep -n body.iter /root/paper-toolbox/modules/doc_parser.py || true")
run(
    "journalctl business-ish lines",
    r"journalctl -u paper-toolbox --no-pager -n 3000 2>&1 "
    r"| grep -v ScriptRunContext | grep -v InsecureRequestWarning | grep -v 'warnings.warn' "
    r"| grep -E 'Step |发现|角标|ERROR|Traceback|Exception|论文标题|目标比例' | tail -50",
)
ssh.close()
