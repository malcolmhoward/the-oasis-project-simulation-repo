"""GPU adapter telemetry through the Windows kernel-mode thunk (D3DKMT) interface in gdi32.dll.

This is the source Task Manager uses for GPU temperature. Layouts and enum values are taken from the
Windows SDK header shared/d3dkmthk.h (10.0.19041.0):

    KMTQAITYPE_ADAPTERREGISTRYINFO = 8
    KMTQAITYPE_ADAPTERPERFDATA     = 62
    D3DKMT_ADAPTER_PERFDATA.Power        "Power draw of the adapter in tenths of a percentage"
    D3DKMT_ADAPTER_PERFDATA.Temperature  "Temperature in deci-Celsius 1 = 0.1C"

Power here is a share of the board power limit, not watts. Utilization is not part of this structure;
see pdh.py. No administrator rights are needed.
"""
import ctypes as C
import sys
from ctypes import wintypes as W

KMTQAITYPE_ADAPTERREGISTRYINFO = 8
KMTQAITYPE_ADAPTERPERFDATA = 62
MAX_PATH = 260
STATUS_SUCCESS = 0
STATUS_BUFFER_TOO_SMALL = 0xC0000023


class LUID(C.Structure):
    _fields_ = [("LowPart", W.DWORD), ("HighPart", W.LONG)]


class D3DKMT_ADAPTERINFO(C.Structure):
    _fields_ = [("hAdapter", C.c_uint32), ("AdapterLuid", LUID), ("NumOfSources", W.ULONG),
                ("bPresentMoveRegionsPreferred", W.BOOL)]


class D3DKMT_ENUMADAPTERS2(C.Structure):
    _fields_ = [("NumAdapters", W.ULONG), ("pAdapters", C.POINTER(D3DKMT_ADAPTERINFO))]


class D3DKMT_QUERYADAPTERINFO(C.Structure):
    _fields_ = [("hAdapter", C.c_uint32), ("Type", C.c_int), ("pPrivateDriverData", C.c_void_p),
                ("PrivateDriverDataSize", W.UINT)]


class D3DKMT_ADAPTERREGISTRYINFO(C.Structure):
    _fields_ = [("AdapterString", C.c_wchar * MAX_PATH), ("BiosString", C.c_wchar * MAX_PATH),
                ("DacType", C.c_wchar * MAX_PATH), ("ChipType", C.c_wchar * MAX_PATH)]


class D3DKMT_ADAPTER_PERFDATA(C.Structure):
    _fields_ = [("PhysicalAdapterIndex", C.c_uint32), ("MemoryFrequency", C.c_uint64),
                ("MaxMemoryFrequency", C.c_uint64), ("MaxMemoryFrequencyOC", C.c_uint64),
                ("MemoryBandwidth", C.c_uint64), ("PCIEBandwidth", C.c_uint64), ("FanRPM", W.ULONG),
                ("Power", W.ULONG), ("Temperature", W.ULONG), ("PowerStateOverride", C.c_ubyte)]


class D3DKMT_CLOSEADAPTER(C.Structure):
    _fields_ = [("hAdapter", C.c_uint32)]


class D3DKMT_DEVICE_IDS(C.Structure):
    _fields_ = [("VendorID", W.UINT), ("DeviceID", W.UINT), ("SubVendorID", W.UINT), ("SubSystemID", W.UINT),
                ("RevisionID", W.UINT), ("BusType", W.UINT)]


class D3DKMT_QUERY_DEVICE_IDS(C.Structure):
    _fields_ = [("PhysicalAdapterIndex", W.UINT), ("DeviceIds", D3DKMT_DEVICE_IDS)]


KMTQAITYPE_PHYSICALADAPTERDEVICEIDS = 31


def luid_instance(luid_low, luid_high):
    """The LUID as it appears in GPU performance-counter instance names: luid_0x<high>_0x<low>."""
    return f"luid_0x{luid_high & 0xFFFFFFFF:08x}_0x{luid_low & 0xFFFFFFFF:08x}"


class Adapter:
    def __init__(self, gdi, info):
        self._gdi = gdi
        self.handle = info.hAdapter
        self.luid_low, self.luid_high = info.AdapterLuid.LowPart, info.AdapterLuid.HighPart
        reg = D3DKMT_ADAPTERREGISTRYINFO()
        ok = self._query(KMTQAITYPE_ADAPTERREGISTRYINFO, reg)
        self.name = (reg.AdapterString or reg.ChipType or "").strip() if ok else ""
        self.chip = reg.ChipType.strip() if ok else ""

    @property
    def luid(self):
        return luid_instance(self.luid_low, self.luid_high)

    def pci_ids(self):
        """(vendor, device) PCI IDs, the key that matches this adapter in vendor telemetry libraries; None if
        the driver does not report them (the Basic Render Driver, for example)."""
        q = D3DKMT_QUERY_DEVICE_IDS(0)
        if not self._query(KMTQAITYPE_PHYSICALADAPTERDEVICEIDS, q) or not q.DeviceIds.VendorID:
            return None
        return q.DeviceIds.VendorID, q.DeviceIds.DeviceID

    def _query(self, kind, struct):
        q = D3DKMT_QUERYADAPTERINFO(self.handle, kind, C.cast(C.pointer(struct), C.c_void_p), C.sizeof(struct))
        return (self._gdi.D3DKMTQueryAdapterInfo(C.byref(q)) & 0xFFFFFFFF) == STATUS_SUCCESS

    def perfdata(self, physical_index=0):
        """Temperature (deg C), power (% of limit) and fan RPM, or None where the driver reports nothing."""
        p = D3DKMT_ADAPTER_PERFDATA()
        p.PhysicalAdapterIndex = physical_index
        if not self._query(KMTQAITYPE_ADAPTERPERFDATA, p):
            return None
        return {"temp_c": p.Temperature / 10.0 if p.Temperature else None,
                "power_pct": p.Power / 10.0 if p.Power else None,
                "fan_rpm": p.FanRPM if p.FanRPM else None}

    def close(self):
        self._gdi.D3DKMTCloseAdapter(C.byref(D3DKMT_CLOSEADAPTER(self.handle)))


def enum_adapters():
    """All adapters D3DKMT reports. The caller closes them."""
    if sys.platform != "win32":
        raise OSError("D3DKMT is Windows-only")
    gdi = C.WinDLL("gdi32")
    e = D3DKMT_ENUMADAPTERS2(0, None)
    gdi.D3DKMTEnumAdapters2(C.byref(e))                       # first call: count only
    buf = (D3DKMT_ADAPTERINFO * max(e.NumAdapters, 1))()
    e.pAdapters = C.cast(buf, C.POINTER(D3DKMT_ADAPTERINFO))
    status = gdi.D3DKMTEnumAdapters2(C.byref(e)) & 0xFFFFFFFF
    if status != STATUS_SUCCESS:
        raise OSError(f"D3DKMTEnumAdapters2 failed: 0x{status:08X}")
    return [Adapter(gdi, buf[i]) for i in range(e.NumAdapters)]


def fresh_perfdata(luid):
    """Perf data through a newly opened handle for the adapter with this LUID, closed again at once, so a stuck
    handle cannot freeze readings. None if the adapter is gone or the query fails."""
    adapters = enum_adapters()
    try:
        for a in adapters:
            if a.luid == luid:
                return a.perfdata()
        return None
    finally:
        for a in adapters:
            a.close()


def select_adapter(adapters, match):
    """The one adapter whose name contains `match` (case-insensitive); an error if none or several do."""
    hits = [a for a in adapters if match.lower() in a.name.lower()]
    if len(hits) != 1:
        names = ", ".join(f"{a.name or '?'} ({a.luid})" for a in adapters)
        raise SystemExit(f"--adapter {match!r} matched {len(hits)} adapters; available: {names}")
    return hits[0]
