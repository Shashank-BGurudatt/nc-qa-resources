# nc-qa-automation

# UI Resources

To use UI test scripts, the please make sure to have Node.js installed on your windows/ mac.

# DSL Resources

Python scripts for managing and analysing **Nutanix Calm / NCM** runbook and app operations at scale.  
These tools are designed to work alongside the [calm-dsl](https://github.com/nutanix/calm-dsl) virtual environment and the NCM REST API.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.11+ |
| calm-dsl | Installed in `~/calm-dsl/venv` (or pass `--calm-dsl-dir`) |
| NCM access | PC credentials configured in `~/.calm/config.ini` |
| Python packages | `matplotlib`, `plotly`, `requests` — install with `pip install matplotlib plotly requests` |

---

## Files

### `calm_create_n_endpoints.py`
**Create N Calm endpoints from matching VMs.**

Discovers VMs on a NCM that match a name pattern and registers them as Calm endpoints (SSH type), grouping VMs per endpoint as specified.

```bash
python3 calm_create_n_endpoints.py \
  --vm_pattern "pcthreevm-*" \
  --n 150 \
  --vms_per_endpoint 1 \
  --name_prefix "cs_endpoints" \
  --account "SolutionPCthree" \
  --project "projectbk" \
  --ssh_user "centos" \
  --ssh_pass "nutanix/4u" \
  --nc_host "nconprem-10-122-152-117.ccpnx.com"
```

**Key arguments:**

| Argument | Description |
|---|---|
| `--vm_pattern` | VM name glob pattern (e.g. `pcthreevm-*`) |
| `--n` | Number of endpoints to create |
| `--name_prefix` | Prefix for generated endpoint names |
| `--vms_per_endpoint` | How many VMs to assign per endpoint |
| `--account` | Calm provider account name |
| `--project` | Calm project name |
| `--ssh_user / --ssh_pass` | SSH credentials for the endpoint |
| `--nc_host` | NCM hostname (optional override) |

---

### `calm_delete_endpoints.py`
**Delete Calm endpoints by prefix+count or name pattern.**

Removes endpoints from Calm, either by generating names from a prefix+count or by matching a glob pattern against existing endpoints.

```bash
# Delete by count
python3 calm_delete_endpoints.py --n 50 --name_prefix cs_endpoints

# Delete by pattern
python3 calm_delete_endpoints.py --pattern "cs_endpoints*"
```

**Key arguments:**

| Argument | Description |
|---|---|
| `--n` | Number of endpoints to delete (used with `--name_prefix`) |
| `--name_prefix` | Endpoint name prefix (default: `endpoint_user`) |
| `--pattern` | Glob pattern to match endpoint names for deletion |
| `--calm-dsl-dir` | Path to calm-dsl checkout (default: `~/calm-dsl`) |

---

### `parallel_calm_delete.py`
**Delete multiple Calm apps in parallel.**

Fetches all Calm apps, filters by a name pattern, and deletes matching apps concurrently using a thread pool. Supports three execution modes and handles large app counts (>250) by iteratively fetching and deleting.

```bash
python3 /Users/chandra.shekharb/Downloads/parallel_calm_delete.py --app-name-pattern "fivejunesmallapp"  --project projectbk --calm_dsl_dir "/Users/chandra.shekharb/calm-dsl"
```

**Key features:**
- Parallel deletion with configurable thread count
- Skips apps already in `deleting` state
- Retries failed deletions with exponential backoff
- Three execution modes (queue / batch / direct)
- Comprehensive logging to console and file

---

### `parallel_calm_launch_v12.py`
**Reference script — Parallel runbook execution with full per-thread logging.**

Launches multiple `calm run runbook` commands concurrently, streaming the complete stdout/stderr of each subprocess into a dedicated per-endpoint log file in real time (using `pexpect`). Supports batching, staggered submission, and multiple execution modes.

```bash
python3 ~/Downloads/parallel_calm_launch_v12.py \
  --item BK-Chandra \
  --base_app_name  bktestapp \
  --project projectbk \
  --environment envpc3 \
  --version 1.0.0 \
  --scheduling \
  --host nconprem-10-122-152-117.ccpnx.com \
  --parallel_users 10 \
  --count 10 \
  --calm_dsl_dir "/Users/chandra.shekharb/calm-dsl" \
  --log_file ~/Downloads/logbktestapp/parallel_calm_launch_$(date +%Y%m%d_%H%M%S).log
```

**Key features:**
- Real-time per-thread log streaming via `pexpect`
- Batching for large endpoint counts
- Staggered submission to avoid NCM throttling
- Multiple modes for different parallelism strategies

---

### `runbook_execution_stats.py`
**Fetch runbook execution data from the NCM API and generate visual reports.**

Given a **batch ID** (the epoch timestamp appended to execution names by the parallel scripts), this tool queries the NCM runlog API, auto-detects the operation type, and produces:
- Scatter plot: endpoint vs. start time (concurrency view)
- Bar chart: duration per endpoint
- Interactive HTML report with expandable per-task audit logs

```bash
# Basic report
python3 runbook_execution_stats.py \
  --calm-dsl-dir ~/calm-dsl \
  --batch-id 1781083084

# With expandable audit logs in the HTML table
python3 runbook_execution_stats.py \
  --calm-dsl-dir ~/calm-dsl \
  --batch-id 1781083084 \
  --fetch-audit

# Using direct credentials
python3 runbook_execution_stats.py \
  --host nconprem-10-122-152-117.ccpnx.com \
  --user admin --pass nutanix/4u \
  --batch-id 1781083084
```

**Output** (written to `./runbook_batch_<id>_<operation>/`):

| File | Description |
|---|---|
| `<id>_<op>_start_times.png` | Scatter plot of execution start times |
| `<id>_<op>_duration.png` | Bar chart of per-endpoint durations |
| `<id>_<op>_report.html` | Full interactive HTML report |

**Key arguments:**

| Argument | Description |
|---|---|
| `--batch-id` | Epoch timestamp from execution names (required) |
| `--calm-dsl-dir` | calm-dsl dir (uses stored credentials) |
| `--host / --user / --pass` | Direct NCM credentials (alternative to DSL) |
| `--fetch-audit` | Fetch per-task audit logs; adds expandable rows to HTML table |
| `--audit-workers` | Parallel workers for audit fetching (default: 10) |
| `--operation` | Override operation label (auto-detected if omitted) |
| `--output` | Custom output file prefix |

---

### `runbook_stats.py`
**Comprehensive NCM runbook execution statistics analyzer.**

Fetches runbook runlogs from the NCM API, extracts detailed execution metrics (task names, states, users, projects, endpoints, timings), and generates in-depth HTML reports with:
- Task hierarchy showing runbook workflows and task relationships
- Performance statistics: min / max / average / P95 execution times
- Scatter plots, bar charts, and trend analysis graphs
- CSV export
- Filtering by task name (regex) and execution state

```bash
python3 runbook_stats.py \
  --host nconprem-10-122-152-117.ccpnx.com \
  --user admin --pass nutanix/4u \
  --runbook-name vmpoweroff
```

---

### `update_stats.py`
**NCM app provisioning statistics analyzer.**

Fetches app runlogs from the NCM API for a given blueprint/app, extracts provisioning timings, and generates:
- Scatter plots of provisioning start times per endpoint
- Bar charts of provisioning duration per app
- Interactive Plotly HTML reports
- CSV exports

Used as a reference for API-based data extraction and visualization patterns.

```bash
python3 /Users/chandra.shekharb/Downloads/update_stats.py --host nconprem-10-122-152-117.ccpnx.com  --app-name flone
```

---

## How the batch ID connects scripts

The parallel execution scripts (`parallel_calm_launch_v12.py`) embed an epoch timestamp into each execution name:

```
par_cs_endpoints1_power_off_1781083084
               ↑                    ↑
           endpoint            batch ID
```

Pass this batch ID to `runbook_execution_stats.py` or `runbook_stats.py` to pull and visualise results for exactly that run.

---

## Log structure

All parallel scripts write logs under `~/.calm/`:

```
~/.calm/
  parallel_runbook_dsl_logs/
    power_off_20260611_093000/
      run.log              ← full console log
      cs_endpoints1.log    ← per-endpoint log
      cs_endpoints2.log
      summary.csv          ← per-task timeline
      ui_summary.csv       ← Calm UI columns
```
