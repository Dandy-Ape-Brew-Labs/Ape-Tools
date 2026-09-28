# sys-info

Reasonable defaults need host awareness: how much RAM can a local
model take, is there disk headroom before that download, is a GPU
actually present, is the laptop about to die on battery.

```sh
sys_info.py            # everything
sys_info.py mem gpu    # just memory + GPU sections
```

- Sizes in bytes; `mem.cgroup_limit`/`cpu.cgroup_quota_cores` surface
  container caps when running sandboxed.
- GPU: `nvidia-smi` stats when installed, otherwise a DRM device count.
- Every section is independent — a missing `/sys` file yields `null`,
  not a failure.
