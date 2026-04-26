#!/usr/bin/env python3
"""
apply-pwa-patch.py  v1.0
========================
Surgically patches index.html to add PWA support:
  1. Adds <link rel="manifest"> and theme-color meta in <head>
  2. Adds <link rel="apple-touch-icon"> for iOS home-screen icon
  3. Adds service-worker registration before </body>
  4. Cache-busts the fetch('events.json') call

Idempotent: running it twice does nothing the second time.

Usage:
    python apply-pwa-patch.py path/to/index.html
"""
import sys
import re
from pathlib import Path

MARKER = "<!-- PWA-PATCH-v1 -->"

HEAD_INSERT = f"""{MARKER}
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#5C1A1A">
<link rel="apple-touch-icon" href="icons/icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="BAPS Timeline">
"""

SW_INSERT = f"""{MARKER}
<script>
if ('serviceWorker' in navigator) {{
  window.addEventListener('load', () => {{
    navigator.serviceWorker.register('service-worker.js')
      .then(reg => console.log('SW registered:', reg.scope))
      .catch(err => console.log('SW registration failed:', err));
  }});
}}
</script>
"""

def main():
    if len(sys.argv) != 2:
        print("Usage: python apply-pwa-patch.py path/to/index.html")
        sys.exit(1)
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"File not found: {p}")
        sys.exit(1)

    html = p.read_text(encoding="utf-8")

    if MARKER in html:
        print("Already patched (marker found). Nothing to do.")
        return

    # 1. Insert head additions just before </head>
    if "</head>" not in html:
        print("ERROR: could not find </head> tag")
        sys.exit(1)
    html = html.replace("</head>", HEAD_INSERT + "</head>", 1)

    # 2. Insert service-worker registration just before </body>
    if "</body>" not in html:
        print("ERROR: could not find </body> tag")
        sys.exit(1)
    html = html.replace("</body>", SW_INSERT + "</body>", 1)

    # 3. Cache-bust the events.json fetch
    pattern = r"fetch\(['\"]events\.json['\"]\)"
    new_call = "fetch('events.json?v=' + Date.now())"
    new_html, n = re.subn(pattern, new_call, html)
    if n == 0:
        print("WARNING: could not find fetch('events.json') to cache-bust")
    else:
        print(f"Cache-busted {n} fetch call(s)")
        html = new_html

    # Write back, preserving line endings as-is
    p.write_text(html, encoding="utf-8", newline="")
    print(f"Patched: {p}")
    print("Look for the marker line to verify:")
    print(f"  {MARKER}")

if __name__ == "__main__":
    main()
