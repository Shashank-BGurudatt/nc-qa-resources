#!/usr/bin/env python3
"""
Delete Calm endpoints by prefix+count OR by name pattern.

Usage:
  # By prefix and count
  python3 calm_delete_endpoints.py --n 2
  python3 calm_delete_endpoints.py --n 5 --name_prefix endpoint_user

  # By pattern (wildcards supported)
  python3 calm_delete_endpoints.py --pattern "endpoint_user*"
  python3 calm_delete_endpoints.py --pattern "ep-load-*"
"""

import os, sys, subprocess, argparse, json, fnmatch, threading

DEFAULT_DSL_DIR = os.path.expanduser("~/calm-dsl")


def list_endpoints(calm_bin, env, debug=False):
    """Return list of endpoint names from `calm get endpoints`."""
    names = []

    # ── Strategy 1: table output (default) — parse the Name column ────────
    # calm get endpoints prints a table like:
    #   NAME             TYPE    ...
    #   endpoint_user1   Linux   ...
    try:
        r = subprocess.run(
            [calm_bin, "get", "endpoints", "--limit", "250"],
            capture_output=True, text=True,
            stdin=subprocess.DEVNULL, env=env, timeout=60,
        )
        if debug:
            print("\n[debug] calm get endpoints stdout:")
            print(r.stdout or "(empty)")
            print("[debug] stderr:", r.stderr or "(empty)")
        for line in (r.stdout or "").splitlines():
            stripped = line.strip()
            # Skip separator lines (+---+) and empty lines
            if not stripped or stripped.startswith("+"):
                continue
            # Table rows look like: | endpoint_user1 | Linux | ...
            # Split on '|' and take the second column (index 1)
            if "|" in stripped:
                cols = [c.strip() for c in stripped.split("|")]
                # cols[0] is empty (before first |), cols[1] is NAME
                if len(cols) > 1:
                    name = cols[1]
                    # Skip the header row
                    if name and name != "NAME":
                        names.append(name)
            else:
                # Non-pipe table format — first token is the name
                parts = stripped.split()
                if parts and parts[0] != "NAME":
                    names.append(parts[0])
        if names:
            return names
    except Exception as ex:
        if debug:
            print(f"[debug] strategy-1 error: {ex}")

    # ── Strategy 2: JSON output — try multiple key structures ─────────────
    try:
        r = subprocess.run(
            [calm_bin, "get", "endpoints", "--limit", "250", "-o", "json"],
            capture_output=True, text=True,
            stdin=subprocess.DEVNULL, env=env, timeout=60,
        )
        raw = (r.stdout or "").strip()
        if debug:
            print("\n[debug] calm get endpoints -o json output:")
            print(raw[:2000])
        # calm sometimes wraps JSON in extra text — find the first '{'
        brace = raw.find("{")
        if brace != -1:
            raw = raw[brace:]
        data = json.loads(raw)

        # Walk every possible nesting calm-dsl may use
        entities = (data.get("entities")
                    or data.get("entity_list")
                    or data.get("response", {}).get("entities")
                    or [])
        for e in entities:
            name = (e.get("status", {}).get("name")
                    or e.get("spec", {}).get("name")
                    or e.get("metadata", {}).get("name")
                    or e.get("name", ""))
            if name:
                names.append(name)
        if names:
            return names
    except Exception as ex:
        if debug:
            print(f"[debug] strategy-2 error: {ex}")

    return names


def delete_endpoint(name, calm_bin, env):
    try:
        r = subprocess.run(
            [calm_bin, "delete", "endpoint", name],
            capture_output=True, text=True,
            input="yes\n",          # auto-confirm any deletion prompt
            env=env, timeout=60,
        )
        out = (r.stdout + r.stderr).strip()
        if r.returncode == 0:
            print(f"  ✓ Deleted {name}")
            return True
        else:
            print(f"  ✗ Failed  {name} (rc={r.returncode}): {out[:150]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout {name}")
        return False
    except Exception as e:
        print(f"  ✗ Error   {name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Delete Calm VM endpoints")

    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--n", type=int,
                     help="Delete <prefix>1 .. <prefix>N")
    src.add_argument("--pattern",
                     help="Wildcard pattern, e.g. 'endpoint_user*' or 'ep-load-?'")

    parser.add_argument("--name_prefix", default="endpoint_user",
                        help="Endpoint name prefix used with --n  (default: endpoint_user)")
    parser.add_argument("--calm_dsl_dir", default=DEFAULT_DSL_DIR)
    parser.add_argument("--debug", action="store_true",
                        help="Print raw calm output to diagnose detection issues")
    args = parser.parse_args()

    venv_bin = os.path.join(args.calm_dsl_dir, "venv", "bin")
    calm_bin = os.path.join(venv_bin, "calm")
    if not os.path.exists(calm_bin):
        calm_bin = "calm"

    env = os.environ.copy()
    if os.path.isdir(venv_bin):
        env["VIRTUAL_ENV"] = os.path.join(args.calm_dsl_dir, "venv")
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")

    # ── Build the list of endpoint names to delete ────────────────────────────
    if args.n:
        names = [f"{args.name_prefix}{i}" for i in range(1, args.n + 1)]
        print(f"Targeting {len(names)} endpoint(s): "
              f"{args.name_prefix}1 .. {args.name_prefix}{args.n}")
    else:
        print(f"Fetching endpoint list to match pattern '{args.pattern}' ...")
        all_names = list_endpoints(calm_bin, env, debug=args.debug)
        if args.debug:
            print(f"[debug] All endpoints found: {all_names}")
        names     = sorted(n for n in all_names if fnmatch.fnmatch(n, args.pattern))
        if not names:
            print(f"No endpoints matched pattern '{args.pattern}'. Nothing to delete.")
            sys.exit(0)
        print(f"Matched {len(names)} endpoint(s): {', '.join(names)}")

    # ── Delete all endpoints in parallel ─────────────────────────────────────
    print()
    results = {}
    lock    = threading.Lock()

    def _delete(name):
        success = delete_endpoint(name, calm_bin, env)
        with lock:
            results[name] = success

    threads = [threading.Thread(target=_delete, args=(name,), daemon=True)
               for name in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok   = sum(1 for v in results.values() if v)
    fail = sum(1 for v in results.values() if not v)
    print(f"\nDone: {ok}/{len(names)} deleted"
          + (f"  ({fail} failed)" if fail else ""))
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
