"""Host resource snapshot — CPU, memory, disk, GPU, power, network.

  sys_info.py              # all sections
  sys_info.py mem          # just memory (incl. cgroup limits)
  sys_info.py gpu power

Reasonable defaults and flags need host awareness: RAM for context
sizing, disk headroom before downloads, GPU presence before picking
local-model backends, battery before long jobs. Linux-first; missing
data degrades to null rather than failing.
"""

import json
import os
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None


def cpu() -> dict:
    model = None
    for line in (read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    out = {"model": model, "cores": os.cpu_count(),
           "load": list(os.getloadavg()) if hasattr(os, "getloadavg") else None}
    # cgroup v2 cpu quota: "MAX|quota period"
    cg = (read("/sys/fs/cgroup/cpu.max") or "").split()
    if len(cg) == 2 and cg[0] != "max":
        out["cgroup_quota_cores"] = round(int(cg[0]) / int(cg[1]), 2)
    return out


def mem() -> dict:
    info = {}
    for line in (read("/proc/meminfo") or "").splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            info[key] = int(rest.strip().split()[0]) * 1024
    out = {"total": info.get("MemTotal"),
           "available": info.get("MemAvailable"),
           "swap_total": info.get("SwapTotal"),
           "swap_free": info.get("SwapFree")}
    limit = read("/sys/fs/cgroup/memory.max")
    if limit and limit != "max":
        out["cgroup_limit"] = int(limit)
        cur = read("/sys/fs/cgroup/memory.current")
        out["cgroup_current"] = int(cur) if cur else None
    return out


def disk() -> dict:
    u = shutil.disk_usage(str(Path.cwd()))
    return {"path": str(Path.cwd()), "total": u.total,
            "used": u.used, "free": u.free}


def gpu() -> dict:
    out = {"nvidia": None, "drm_devices": 0}
    if agentlib.which("nvidia-smi"):
        r = agentlib.run_cmd(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,"
             "driver_version", "--format=csv,noheader,nounits"])
        if r["ok"]:
            out["nvidia"] = [
                {"name": p[0].strip(), "mem_total_mb": int(p[1]),
                 "mem_used_mb": int(p[2]), "driver": p[3].strip()}
                for line in r["stdout"].strip().splitlines()
                if len(p := line.split(",")) >= 4]
    drm = Path("/sys/class/drm")
    if drm.is_dir():
        out["drm_devices"] = len([c for c in drm.iterdir()
                                  if c.name.startswith("card")
                                  and "-" not in c.name])
    return out


def power() -> dict:
    supplies = Path("/sys/class/power_supply")
    out = {"ac_online": None, "batteries": []}
    if not supplies.is_dir():
        return out
    for s in supplies.iterdir():
        typ = read(str(s / "type"))
        if typ == "Battery":
            cap = read(str(s / "capacity"))
            out["batteries"].append({
                "name": s.name,
                "capacity_pct": int(cap) if cap and cap.isdigit() else None,
                "status": read(str(s / "status"))})
        elif typ in ("Mains", "USB", "ADP") or s.name.startswith("AC"):
            online = read(str(s / "online"))
            out["ac_online"] = bool(int(online)) if online is not None else None
    return out


def net() -> dict:
    ifaces = {}
    for line in (read("/proc/net/dev") or "").splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name == "lo":
            continue
        cols = rest.split()
        if len(cols) >= 9:
            ifaces[name] = {"rx_bytes": int(cols[0]),
                            "tx_bytes": int(cols[8])}
    return {"interfaces": ifaces}


def meta() -> dict:
    return {"hostname": platform.node(), "system": platform.system(),
            "release": platform.release(), "machine": platform.machine(),
            "python": platform.python_version(),
            "uptime_s": float((read("/proc/uptime") or "0").split()[0])}


SECTIONS = {"cpu": cpu, "mem": mem, "disk": disk, "gpu": gpu,
            "power": power, "net": net, "meta": meta}


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("sections", nargs="*", default=None,
                   choices=[*SECTIONS, "all"],
                   help=f"sections: {', '.join(SECTIONS)} or all (default)")
    args = p.parse_args()
    names = (list(SECTIONS) if not args.sections or "all" in args.sections
             else args.sections)
    out = {}
    for name in names:
        try:
            out[name] = SECTIONS[name]()
        except Exception as exc:
            out[name] = {"error": str(exc)}
    agentlib.emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
