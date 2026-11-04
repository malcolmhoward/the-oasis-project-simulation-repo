"""Windows performance counters (PDH) for GPU utilization, GPU memory and system CPU, via pdh.dll.

GPU utilization is computed the way Task Manager does: per engine type, the sum over processes of
"\\GPU Engine(*)\\Utilization Percentage", restricted to one adapter's LUID. Instance names look like
    pid_1234_luid_0x00000000_0x0000d1b5_phys_0_eng_3_engtype_Compute
"""
import ctypes as C
import re
import sys
from ctypes import wintypes as W

PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
PDH_MORE_DATA = 0x800007D2
PDH_CSTATUS_VALID_DATA = 0x0
PDH_CSTATUS_NEW_DATA = 0x1

GPU_ENGINE = r"\GPU Engine(*)\Utilization Percentage"
GPU_DEDICATED = r"\GPU Adapter Memory(*)\Dedicated Usage"
CPU_TOTAL = r"\Processor(_Total)\% Processor Time"

_ENGINE = re.compile(r"(luid_0x[0-9a-f]{8}_0x[0-9a-f]{8})_phys_(\d+)_eng_\d+_engtype_(.*)$", re.I)
_ADAPTER = re.compile(r"(luid_0x[0-9a-f]{8}_0x[0-9a-f]{8})_phys_(\d+)$", re.I)


class _Value(C.Union):
    _fields_ = [("longValue", W.LONG), ("doubleValue", C.c_double), ("largeValue", C.c_longlong),
                ("AnsiStringValue", C.c_char_p), ("WideStringValue", C.c_wchar_p)]


class PDH_FMT_COUNTERVALUE(C.Structure):
    _fields_ = [("CStatus", W.DWORD), ("u", _Value)]


class PDH_FMT_COUNTERVALUE_ITEM_W(C.Structure):
    _fields_ = [("szName", C.c_wchar_p), ("FmtValue", PDH_FMT_COUNTERVALUE)]


def engine_utilization(items, luid):
    """{engine type: utilization %} for one adapter from (instance name, value) pairs. Each engine type is
    the sum over processes, capped at 100, as Task Manager shows it."""
    out = {}
    for name, value in items:
        m = _ENGINE.search(name)
        if not m or m.group(1).lower() != luid.lower():
            continue
        etype = m.group(3).strip() or "unknown"
        out[etype] = out.get(etype, 0.0) + value
    return {k: min(v, 100.0) for k, v in out.items()}


def adapter_value(items, luid):
    """Sum of an adapter-memory counter over the physical adapters of one LUID, or None if absent."""
    vals = [v for n, v in items if (m := _ADAPTER.search(n)) and m.group(1).lower() == luid.lower()]
    return sum(vals) if vals else None


class Query:
    """A PDH query over a fixed set of (possibly wildcard) counter paths. Rate counters such as utilization
    need two collections, so the first sample() after construction primes them."""

    def __init__(self, paths):
        if sys.platform != "win32":
            raise OSError("PDH is Windows-only")
        self._pdh = C.WinDLL("pdh")
        self._q = W.HANDLE()
        self._check(self._pdh.PdhOpenQueryW(None, None, C.byref(self._q)), "PdhOpenQueryW")
        self._counters = {}
        for p in paths:
            h = W.HANDLE()
            rc = self._pdh.PdhAddEnglishCounterW(self._q, p, None, C.byref(h))
            if rc == 0:
                self._counters[p] = h
        self.missing = [p for p in paths if p not in self._counters]
        self._pdh.PdhCollectQueryData(self._q)

    @staticmethod
    def _check(rc, what):
        if rc & 0xFFFFFFFF:
            raise OSError(f"{what} failed: 0x{rc & 0xFFFFFFFF:08X}")

    def sample(self):
        """{path: [(instance, value), ...]} for every counter that was added."""
        self._pdh.PdhCollectQueryData(self._q)
        out = {}
        for path, h in self._counters.items():
            size, count = W.DWORD(0), W.DWORD(0)
            rc = self._pdh.PdhGetFormattedCounterArrayW(h, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, C.byref(size),
                                                         C.byref(count), None) & 0xFFFFFFFF
            if rc != PDH_MORE_DATA or not size.value:
                out[path] = []
                continue
            buf = C.create_string_buffer(size.value)
            rc = self._pdh.PdhGetFormattedCounterArrayW(h, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, C.byref(size),
                                                         C.byref(count), buf) & 0xFFFFFFFF
            if rc:
                out[path] = []
                continue
            items = C.cast(buf, C.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
            out[path] = [(items[i].szName or "", items[i].FmtValue.u.doubleValue) for i in range(count.value)
                         if items[i].FmtValue.CStatus in (PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA)]
        return out

    def close(self):
        self._pdh.PdhCloseQuery(self._q)
