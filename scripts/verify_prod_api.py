#!/usr/bin/env python3
"""
verify_prod_api.py
MunshiAI Production Endpoint Verification Suite
Uses standard library urllib to avoid external dependencies.
"""

import json
import urllib.request
import urllib.error
import ssl

# Target hosts
TARGETS = {
    "Main Website": "https://munshiai.co.in",
    "API Root": "https://munshiai.co.in/api",
    "Billing Plans API": "https://munshiai.co.in/api/billing/plans",
    "Staff API (Auth Guarded)": "https://munshiai.co.in/api/v1/staff/list",
    "n8n Automation Portal": "https://n8n.munshiai.co.in",
    "DB Admin Portal (Adminer)": "https://db.munshiai.co.in"
}

def check_endpoint(name, url, method="GET", data=None):
    print(f"[*] Testing {name:<26} | URL: {url}...")
    
    # Create request
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "MunshiAI-Diagnostic-Agent/1.0")
    
    if data:
        req.add_header("Content-Type", "application/json")
        req_data = json.dumps(data).encode("utf-8")
    else:
        req_data = None

    # Disable SSL verification issues if testing flexible SSL transitions
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, data=req_data, timeout=8, context=ctx) as response:
            status = response.status
            body = response.read().decode("utf-8")
            
            print(f"    [+] Status: {status} OK")
            # Try parsing json if applicable
            try:
                parsed = json.loads(body)
                print(f"    [+] Content: JSON Received ({len(parsed)} items/keys)")
            except json.JSONDecodeError:
                snippet = body[:100].replace('\n', ' ').strip()
                print(f"    [+] Content Snippet: {snippet}...")
            return True, status
            
    except urllib.error.HTTPError as e:
        # Some errors are expected due to authentication/permissions (e.g. 401, 405)
        status = e.code
        body = e.read().decode("utf-8", errors="ignore")
        if status in [401, 403, 405, 422]:
            print(f"    [+] Status: {status} (Expected Behavior for unauthenticated/guarded endpoint)")
            return True, status
        else:
            print(f"    [-] Status: {status} ERROR - HTTP Error")
            print(f"    [-] Detail: {body[:200]}")
            return False, status
            
    except urllib.error.URLError as e:
        print(f"    [-] Connection Failed: {e.reason}")
        return False, None
    except Exception as e:
        print(f"    [-] Unexpected Error: {e}")
        return False, None

def main():
    print("=" * 60)
    print("   MunshiAI Production Endpoint Verification Suite   ")
    print("=" * 60)
    
    success_count = 0
    total = len(TARGETS)
    
    for name, url in TARGETS.items():
        success, code = check_endpoint(name, url)
        if success:
            success_count += 1
        print("-" * 60)
        
    print(f"\n[Verification Summary]: {success_count}/{total} endpoints passed successfully.")
    if success_count == total:
        print("[STATUS] ALL SYSTEMS OPERATIONAL!")
    else:
        print("[WARNING] SOME ENDPOINTS RETURNED ERRORS. Check network, Docker service state, or Cloudflare SSL configurations.")

if __name__ == "__main__":
    main()
