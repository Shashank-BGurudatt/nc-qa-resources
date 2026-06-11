#!/usr/bin/env python3
"""
Create Calm VM endpoints from VMs matching a name pattern.

Steps:
  1. Search all VMs whose name matches a pattern (e.g. "Liteone-*", "vm-?")
  2. Group them into endpoints (N VMs per endpoint)
  3. Create each endpoint using filter-placeholder + PUT-update approach

Usage:
  python3 calm_create_n_endpoints.py \\
      --calm_dsl_dir ~/calm-dsl \\
      --vm_pattern   "Liteone-*" \\
      --vms_per_endpoint 2 \\
      --name_prefix  "ep-load" \\
      --account      "SolutionPCthree" \\
      --project      "projectbk" \\
      --ssh_user     centos \\
      --ssh_pass     "nutanix/4u"

  # 1 VM per endpoint:
  ... --vm_pattern "vm-*" --vms_per_endpoint 1

  # Limit total endpoints even if more VMs exist:
  ... --vm_pattern "vm-*" --vms_per_endpoint 2 --max_endpoints 5
"""

import os, sys, json, argparse, subprocess, tempfile, time, threading, fnmatch, configparser
from datetime import datetime

_log_lock = threading.Lock()
_log_fh   = None

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with _log_lock:
        print(line, flush=True)
        if _log_fh:
            try:
                _log_fh.write(line + "\n")
                _log_fh.flush()
            except Exception:
                pass

DEFAULT_DSL_DIR = os.path.expanduser("~/calm-dsl")
DEFAULT_ACCOUNT = "SolutionPCtwo"
DEFAULT_PROJECT = "projectbk"
DEFAULT_NC_HOST = "nconprem-10-122-152-117.ccpnx.com"

# ── Helper (runs inside calm-dsl venv) ───────────────────────────────────────
_HELPER = r'''
import sys, json, copy, fnmatch

task = sys.argv[1]
args = sys.argv[2:]

try:
    from calm.dsl.api import get_api_client
    from calm.dsl.api.connection import REQUEST
except ImportError as e:
    print(f"ERROR: {e}"); sys.exit(2)

try:
    import urllib3; urllib3.disable_warnings()
except ImportError:
    pass

client = get_api_client()
conn   = client.runbook.connection

def api(path, method=REQUEST.METHOD.GET, payload=None):
    kwargs = dict(method=method, verify=False, ignore_error=True)
    if payload is not None:
        kwargs["request_json"] = payload
    res, err = conn._call(path, **kwargs)
    if res is not None:
        try:    return res.status_code, res.json()
        except: return res.status_code, {"raw": res.text[:600]}
    return (err or {}).get("code") or 0, err or {}

def find_endpoint(ep_name):
    offset = 0
    while True:
        s, d = api("api/nutanix/v3/endpoints/list", method=REQUEST.METHOD.POST,
                   payload={"length": 50, "offset": offset})
        if s not in (200, 201): break
        for ent in (d.get("entities") or []):
            if (ent.get("metadata") or {}).get("name") == ep_name:
                return (ent.get("metadata") or {}).get("uuid")
        total  = (d.get("metadata") or {}).get("total_matches", 0)
        offset += len(d.get("entities") or [])
        if offset >= total or not d.get("entities"): break
    return None

# ═══════════════════════════════════════════════════════════════════════
# TASK: list_vms  — find all VMs matching a name pattern via NCM
# args[0] = pattern (fnmatch style)
# ═══════════════════════════════════════════════════════════════════════
if task == "list_vms":
    pattern  = args[0]

    # Auto-add wildcard if none present so "firstvm" matches "firstvm-5117"
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"
        print(f"No wildcard in pattern — auto-expanded to '{pattern}'")

    print(f"Searching VMs matching '{pattern}' via NCM ...")

    def _extract_vms(node, out):
        if isinstance(node, dict):
            # Common VM shapes across v3/self-service/app payloads.
            kind = str(node.get("kind", "")).lower()
            name = (node.get("name") or node.get("vm_name") or "")
            uuid = (node.get("uuid") or node.get("vm_uuid") or "")

            status = node.get("status") if isinstance(node.get("status"), dict) else {}
            metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
            spec = node.get("spec") if isinstance(node.get("spec"), dict) else {}
            resources = spec.get("resources") if isinstance(spec.get("resources"), dict) else {}

            if not name:
                name = (status.get("name") or metadata.get("name") or
                        resources.get("name") or "")
            if not uuid:
                uuid = (metadata.get("uuid") or status.get("uuid") or
                        resources.get("uuid") or "")

            if name and uuid and (kind in ("vm", "", "nutanix_vm", "ahv_vm")):
                out.append({"name": str(name), "uuid": str(uuid)})

            for v in node.values():
                _extract_vms(v, out)
        elif isinstance(node, list):
            for x in node:
                _extract_vms(x, out)

    matched = []
    vm_sources = [
        ("api/nutanix/v3/vms/list", {"kind": "vm"}),
        ("api/nutanix/v3/vms/list", {}),
        ("api/self-service/v3/vms/list", {}),
        ("api/self-service/v3/vms", {}),
        ("api/nutanix/v3/apps/list", {"kind": "app"}),
    ]
    source_used = None
    for path, base_payload in vm_sources:
        found_in_source = []
        offset = 0
        while True:
            payload = dict(base_payload)
            payload["length"] = 100
            payload["offset"] = offset
            s, d = api(path, method=REQUEST.METHOD.POST, payload=payload)
            if s not in (200, 201):
                if offset == 0:
                    print(f"  {path} HTTP {s}: {json.dumps(d)[:200]}")
                break

            entities = d.get("entities") or []
            if not entities:
                break

            extracted = []
            for ent in entities:
                _extract_vms(ent, extracted)
            for vm in extracted:
                name, uuid = vm["name"], vm["uuid"]
                if (fnmatch.fnmatch(name.lower(), pattern.lower()) or
                    fnmatch.fnmatch(name, pattern)):
                    found_in_source.append({"name": name, "uuid": uuid})

            total = (d.get("metadata") or {}).get("total_matches", 0)
            offset += len(entities)
            if offset >= total or len(entities) == 0:
                break

        if found_in_source:
            matched.extend(found_in_source)
            source_used = path
            break

    if source_used:
        print(f"  VM source used: {source_used}")

    # Deduplicate by UUID (guards against PC+NCM fallback both succeeding)
    seen  = set()
    dedup = []
    for v in matched:
        if v["uuid"] not in seen:
            seen.add(v["uuid"])
            dedup.append(v)
    matched = dedup

    # Sort numerically by trailing number so firstvm-1 < firstvm-2 < firstvm-10
    # This ensures endpoint_user1 → firstvm-1, endpoint_user2 → firstvm-2, etc.
    import re as _re
    def _num_key(v):
        m = _re.search(r'(\d+)$', v["name"])
        return int(m.group(1)) if m else 0
    matched.sort(key=_num_key)

    print(f"Found {len(matched)} VM(s) matching '{pattern}' (sorted numerically):")
    for i, v in enumerate(matched, 1):
        print(f"  [{i}] {v['name']}  ({v['uuid']})")
    print("RESULT_JSON:" + json.dumps({"vms": matched}))
    sys.exit(0)

# ═══════════════════════════════════════════════════════════════════════
# TASK: get_ep_uuid — look up endpoint UUID and state by name
# ═══════════════════════════════════════════════════════════════════════
elif task == "get_ep_uuid":
    ep_name = args[0]
    ep_uuid = find_endpoint(ep_name)
    if not ep_uuid:
        print("RESULT_JSON:" + json.dumps({"ok": False, "error": "not found"}))
        sys.exit(1)
    s, d = api(f"api/nutanix/v3/endpoints/{ep_uuid}")
    state = (d.get("status") or {}).get("state", "?") if s in (200, 201) else "?"
    print(f"  {ep_name}  uuid={ep_uuid}  state={state}")
    print("RESULT_JSON:" + json.dumps({"ok": True, "uuid": ep_uuid, "state": state}))
    sys.exit(0)

else:
    print(f"ERROR: unknown task '{task}'"); sys.exit(2)
'''


def resolve_venv(calm_dsl_dir):
    for py in [os.path.join(calm_dsl_dir, "venv", "bin", "python3"),
               os.path.join(calm_dsl_dir, "venv", "bin", "python")]:
        if os.path.exists(py):
            return py
    return sys.executable


def resolve_calm(calm_dsl_dir):
    venv_bin = os.path.join(calm_dsl_dir, "venv", "bin")
    calm = os.path.join(venv_bin, "calm")
    if not os.path.exists(calm):
        calm = "calm"
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = os.path.join(calm_dsl_dir, "venv")
    if os.path.isdir(venv_bin):
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    return calm, env


def run_helper(venv_python, helper_path, *args):
    r = subprocess.run(
        [venv_python, helper_path] + list(args),
        capture_output=True, text=True, timeout=120
    )
    result = {}
    for line in (r.stdout or "").strip().splitlines():
        if line.startswith("RESULT_JSON:"):
            try: result = json.loads(line[len("RESULT_JSON:"):])
            except Exception: pass
        else:
            log(f"  [helper] {line}")
    for line in (r.stderr or "").strip().splitlines():
        log(f"  [stderr] {line}")
    return r.returncode, result


def generate_vm_names(pattern, n):
    """Generate N VM names from wildcard or template pattern."""
    if "{}" in pattern:
        return [pattern.replace("{}", str(i)) for i in range(1, n + 1)]
    if "*" in pattern:
        prefix = pattern.split("*", 1)[0]
        suffix = pattern.split("*", 1)[1]
        return [f"{prefix}{i}{suffix}" for i in range(1, n + 1)]
    if "?" in pattern:
        q_count = pattern.count("?")
        names = []
        for i in range(1, n + 1):
            rep = str(i).zfill(q_count)
            name = pattern
            for ch in rep:
                name = name.replace("?", ch, 1)
            names.append(name)
        return names
    return [f"{pattern}-{i}" for i in range(1, n + 1)]


def create_endpoint_dsl(calm, calm_env, ep_name, vm_name,
                         account, project, ssh_user, ssh_pass):
    """Create endpoint via calm CLI DSL using filter='name==<vm>' — same as UI does.

    Using filter='name==<vm>' instead of Ref.Vm(name=...) because:
    - endpointtest (manually created, works) stores filter='name==firstvm-1'
    - Ref.Vm(name=...) creates vm_references but without the filter field,
      so Calm cannot resolve/display the VM in the UI or endpoint picker.
    - Each VM has a unique name so the filter matches exactly one VM.
    """
    dsl_var = ep_name.replace("-", "_").replace(" ", "_")
    content = f"""from calm.dsl.runbooks import CalmEndpoint as Endpoint
from calm.dsl.builtins import Ref, Metadata, basic_cred

DefaultCred = basic_cred(
    "{ssh_user}",
    "{ssh_pass}",
    name="default",
    type="PASSWORD",
    default=True,
)

{dsl_var} = Endpoint.Linux.vm(
    filter="name=={vm_name}",
    account=Ref.Account(name="{account}"),
    cred=DefaultCred,
)

class EndpointMetadata(Metadata):
    project = Ref.Project("{project}")
"""
    fd, path = tempfile.mkstemp(suffix=".py", prefix="ep_dsl_")
    with os.fdopen(fd, "w") as f:
        f.write(content)

    r = subprocess.run(
        [calm, "create", "endpoint", "-f", path, "--name", ep_name, "--force"],
        capture_output=True, text=True, env=calm_env, timeout=120
    )
    combined = (r.stdout or "") + (r.stderr or "")
    try: os.unlink(path)
    except OSError: pass
    return "created successfully" in combined, combined


def main():
    parser = argparse.ArgumentParser(
        description="Create Calm VM endpoints from VMs matching a name pattern",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--calm_dsl_dir",     default=DEFAULT_DSL_DIR)
    parser.add_argument("--vm_pattern",       required=True,
                        help="VM name pattern (e.g. 'Liteone-*', 'vm-?', '*centos*')")
    parser.add_argument("--n",                type=int, required=True,
                        help="Number of endpoints to create")
    parser.add_argument("--vms_per_endpoint", type=int, default=1,
                        help="Number of VMs per endpoint (default: 1)")
    parser.add_argument("--name_prefix",      default="ep-load",
                        help="Endpoint name prefix → ep-load-1, ep-load-2 ...")
    parser.add_argument("--account",          default=DEFAULT_ACCOUNT,
                        help="AHV account name")
    parser.add_argument("--project",          default=DEFAULT_PROJECT)
    parser.add_argument("--nc_host",          default=DEFAULT_NC_HOST,
                        help="Nutanix Central host for logging/reference")
    parser.add_argument("--ssh_user",         default="centos")
    parser.add_argument("--ssh_pass",         default="nutanix/4u")

    _default_log = os.path.join(
        os.path.expanduser("~/Downloads/logs"),
        f"calm_create_endpoints_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    parser.add_argument("--log_file", default=_default_log)
    args = parser.parse_args()

    global _log_fh
    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.log_file)), exist_ok=True)
        _log_fh = open(args.log_file, "w", encoding="utf-8")
        print(f"Logging to: {args.log_file}", flush=True)
    except Exception as e:
        print(f"WARNING: could not open log file: {e}", flush=True)

    venv_python = resolve_venv(args.calm_dsl_dir)
    calm, calm_env = resolve_calm(args.calm_dsl_dir)

    log(f"calm binary      : {calm}")
    log(f"vm_pattern       : {args.vm_pattern}")
    log(f"n (endpoints)    : {args.n}")
    log(f"vms_per_endpoint : {args.vms_per_endpoint}")
    log(f"name_prefix      : {args.name_prefix}")
    log(f"nc_host          : {args.nc_host}")
    log(f"account          : {args.account}")
    log(f"project          : {args.project}")

    fd_h, helper_path = tempfile.mkstemp(suffix=".py", prefix="ep_helper_")
    with os.fdopen(fd_h, "w") as f:
        f.write(_HELPER)

    try:
        # ── Step 1: derive VM list from pattern (deterministic) ─────────────
        log(f"\n{'='*55}")
        total_needed = args.n * args.vms_per_endpoint
        log(f"STEP 1: Generating VM names from pattern '{args.vm_pattern}' "
            f"(count={total_needed}) ...")
        vm_names = generate_vm_names(args.vm_pattern, total_needed)
        vms = [{"name": name, "uuid": ""} for name in vm_names]
        log(f"\nGenerated {len(vms)} VM name(s):")
        for v in vms:
            log(f"  {v['name']}")

        # ── Step 2: build N endpoint groups ──────────────────────────────────
        log(f"\n{'='*55}")
        log(f"STEP 2: Building {args.n} endpoint(s) — {args.vms_per_endpoint} VM(s) each ...")
        log(f"        ({len(vms)} VM(s) available — cycling round-robin if needed)")

        k = args.vms_per_endpoint
        groups = []
        for i in range(args.n):
            grp = [vms[(i * k + j)] for j in range(k)]
            groups.append(grp)

        ep_names = [f"{args.name_prefix}{i+1}" for i in range(args.n)]

        log(f"\nEndpoint plan ({len(groups)} endpoint(s)):")
        for ep_name, grp in zip(ep_names, groups):
            vm_names = [v["name"] for v in grp]
            log(f"  {ep_name}: {vm_names}")

        # ── Step 3: create each endpoint ─────────────────────────────────────
        log(f"\n{'='*55}")
        log(f"STEP 3: Creating {args.n} endpoint(s) via calm CLI DSL (Ref.Vm by name) ...")

        results = []
        for i, (ep_name, grp) in enumerate(zip(ep_names, groups), 1):
            # Each group has exactly vms_per_endpoint VMs; use first VM's name
            vm_name = grp[0]["name"]
            log(f"\n[{i}/{len(groups)}] '{ep_name}' → vm='{vm_name}'")

            # Single-step: calm create endpoint via Ref.Vm(name=...) DSL
            # This matches how endpointtest was manually created in the UI.
            # No filter, no auto_select_vms, no PUT update needed — creates ACTIVE.
            log(f"  Creating via calm CLI DSL (Ref.Vm name='{vm_name}') ...")
            ok, out = create_endpoint_dsl(
                calm, calm_env, ep_name, vm_name,
                args.account, args.project, args.ssh_user, args.ssh_pass
            )

            if ok:
                log(f"  ✓ Created successfully")
                # Fetch UUID and state
                _, res2 = run_helper(venv_python, helper_path, "get_ep_uuid", ep_name)
                ep_uuid  = res2.get("uuid", "?")
                ep_state = res2.get("state", "ACTIVE")
                log(f"  uuid={ep_uuid}  state={ep_state}")
                results.append({"name": ep_name, "ok": True,
                                 "uuid": ep_uuid, "state": ep_state,
                                 "vms": [v["name"] for v in grp]})
            else:
                log(f"  ✗ FAILED — {out.strip()[:200]}")
                results.append({"name": ep_name, "ok": False,
                                 "vms": [v["name"] for v in grp]})

        # ── Summary ───────────────────────────────────────────────────────────
        log(f"\n{'='*55}")
        log("SUMMARY")
        log(f"{'='*55}")
        ok_count   = sum(1 for r in results if r.get("ok") is True)
        fail_count = sum(1 for r in results if not r.get("ok"))

        for r in results:
            ep_state = r.get("state", "?")
            status   = (f"✓ {ep_state}" if r.get("ok") else "✗ FAILED")
            vms_str  = ", ".join(r.get("vms", []))
            log(f"  [{status}] {r['name']}  vm=[{vms_str}]  uuid={r.get('uuid','?')}")

        log(f"\nVMs matched   : {len(vms)}")
        log(f"Endpoints     : {len(groups)}")
        log(f"  ✓ OK        : {ok_count}")
        log(f"  ✗ Failed    : {fail_count}")
        log(f"Log saved to  : {args.log_file}")

    finally:
        try: os.unlink(helper_path)
        except OSError: pass
        if _log_fh:
            try: _log_fh.close()
            except Exception: pass


if __name__ == "__main__":
    main()
