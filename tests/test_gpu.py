"""GPU telemetry: the HAL interface, FailoverProvider, the Layer 0 mock, and the live sources (hardware-free parts,
plus a smoke test that runs only where a real source is present).

    pytest tests/test_gpu.py -q
"""
import ctypes as C
import types

import pytest

from simulation.hal.device import GPU_TELEMETRY_KEYS, GpuTelemetryInterface
from simulation.hal.failover import FailoverProvider
from simulation.hal.status import SimulationStatus, is_mock_implementation
from simulation.layer0.gpu import MockGpuTelemetry
from simulation.live.gpu import discover, hwmon, igcl, levelzero, nvml, wddm
from simulation.live.gpu.base import LiveGpuSource


class Fake(LiveGpuSource):
    def __init__(self, provider, temp=None):
        self.provider, self.name, self.temp = provider, provider, temp

    def capabilities(self):
        return {"temp_c": True}

    def read(self):
        return {"temp_c": self.temp}


# ---- interface and classification ----

def test_mock_and_live_sources_implement_the_interface_and_are_classified():
    assert set(GPU_TELEMETRY_KEYS) == {"temp_c", "power_w", "fan_rpm", "util_pct", "mem_used_mb"}
    mock = MockGpuTelemetry()
    assert isinstance(mock, GpuTelemetryInterface) and is_mock_implementation(mock)
    for cls in (wddm.WddmDevice, igcl.IgclDevice, levelzero.LevelZeroDevice, nvml.NvmlDevice, hwmon.HwmonDevice):
        assert issubclass(cls, GpuTelemetryInterface)
    assert not is_mock_implementation(Fake("real"))          # live sources are real, by explicit flag


# ---- FailoverProvider ----

def test_failover_waits_fail_after_ticks_then_swaps_and_never_flaps():
    a, b = Fake("a", 50.0), Fake("b", 51.0)
    swaps = []
    p = FailoverProvider([a, b], on_swap=lambda o, n: swaps.append((o, n)), fail_after=3, name="gpu.temp")
    assert p.observe({a: 50.0, b: 51.0}) == 50.0 and p.implementation is a
    assert p.observe({a: None, b: 51.0}) is None
    assert p.observe({b: 51.0}) is None                      # a missing key counts as no value
    assert p.observe({a: None, b: 51.5}) == 51.5 and p.implementation is b
    assert swaps == [(a, b)] and "no value from a for 3 ticks" in p.last_swap_reason
    assert p.observe({a: 49.0, b: 52.0}) == 52.0 and len(swaps) == 1   # no swap back on its own


def test_exclusive_pair_gives_two_independent_sources():
    a, b = Fake("a"), Fake("b")
    primary = FailoverProvider([a, b])
    second = FailoverProvider([a, b], exclude=primary)
    assert primary.implementation is a and second.implementation is b
    lone = FailoverProvider([a], exclude=FailoverProvider([a]))
    assert lone.implementation is None and lone.observe({a: 1.0}) is None


def test_failover_works_with_simulation_status():
    status = SimulationStatus("gpu")
    real, mock = Fake("windows-wddm", 60.0), MockGpuTelemetry()
    p = FailoverProvider([real, mock], on_swap=status.create_swap_handler("gpu.temp"), fail_after=1)
    status.register("gpu.temp", p.implementation)
    assert not status.is_any_simulated()
    p.observe({real: None, mock: 41.0})                      # real source fails: fall back to the simulation
    assert p.implementation is mock and status.is_any_simulated()


# ---- Layer 0 mock ----

def test_mock_heats_with_load_and_injects_faults():
    t = [0.0]
    g = MockGpuTelemetry(tau_s=10.0, clock=lambda: t[0])
    g.set_load(95.0)
    first = g.read()["temp_c"]
    t[0] = 60.0
    hot = g.read()["temp_c"]
    assert hot > first + 20
    g.inject(freeze_temp=True)
    frozen = g.read()["temp_c"]
    g.set_load(2.0)
    t[0] = 200.0
    assert g.read()["temp_c"] == frozen
    g.inject(drop_temp=True)
    assert g.read()["temp_c"] is None
    g.clear_faults()
    assert g.read()["temp_c"] not in (None, frozen)
    g.inject(drop_all=True)
    assert g.read() == {}
    with pytest.raises(ValueError, match="unknown fault"):
        g.inject(melt=True)


# ---- live sources, hardware-free parts ----

def test_d3dkmt_layouts_match_the_windows_sdk_header():
    from simulation.live.gpu import d3dkmt
    s = d3dkmt.D3DKMT_ADAPTER_PERFDATA
    assert C.sizeof(s) == 64
    assert (s.MemoryFrequency.offset, s.FanRPM.offset, s.Power.offset, s.Temperature.offset) == (8, 48, 52, 56)
    assert C.sizeof(d3dkmt.D3DKMT_QUERY_DEVICE_IDS) == 28
    assert d3dkmt.luid_instance(0xABCD, 0) == "luid_0x00000000_0x0000abcd"


def test_pdh_engine_utilization_sums_processes_per_type_for_one_adapter():
    from simulation.live.gpu import pdh
    luid, other = "luid_0x00000000_0x0000abcd", "luid_0x00000000_0x0000beef"
    items = [(f"pid_10_{luid}_phys_0_eng_0_engtype_3D", 30.0), (f"pid_11_{luid}_phys_0_eng_0_engtype_3D", 25.0),
             (f"pid_12_{luid}_phys_0_eng_3_engtype_Compute", 80.0), (f"pid_13_{luid}_phys_0_eng_3_engtype_Compute", 40.0),
             (f"pid_14_{other}_phys_0_eng_0_engtype_3D", 99.0)]
    assert pdh.engine_utilization(items, luid.upper()) == {"3D": 55.0, "Compute": 100.0}
    assert pdh.adapter_value([(f"{luid}_phys_0", 2.0 ** 30), (f"{other}_phys_0", 5.0)], luid) == 2 ** 30


def test_vendor_struct_layouts_match_their_headers():
    # Level Zero v1.32 and IGCL headers: spot-check sizes that a field-order mistake would change
    assert C.sizeof(levelzero.zes_power_energy_counter_t) == 16
    assert levelzero.zes_device_properties_t.core.offset == 16
    assert C.sizeof(igcl.ctl_power_energy_counter_t) == 24 and igcl.ctl_power_energy_counter_t.energy.offset == 8
    assert igcl.ctl_device_adapter_properties_t.pDeviceID.offset == 8


def test_discover_matches_by_pci_ids_before_names():
    opened = []

    def mod(name, devs):
        m = types.ModuleType(f"simulation.live.gpu.{name}")
        m.devices = lambda: [(n, ids, (lambda n=n: opened.append(n) or Fake(n))) for n, ids in devs]
        return m
    l0 = mod("levelzero", [("Intel(R) Graphics [0x1111]", (0x8086, 0x1111)), ("Intel(R) Graphics [0x2222]", (0x8086, 0x2222))])
    nv = mod("nvml", [("NVIDIA RTX", (0x10DE, 0x2684))])
    found, report = discover(match="Arc", pci=(0x8086, 0x1111), modules=(l0, nv))
    assert opened == ["Intel(R) Graphics [0x1111]"] and report["nvml"]["matched"] == []
    assert found[0].pci_ids == (0x8086, 0x1111)
    found, _ = discover(match="rtx", modules=(nv,))
    assert [d.name for d in found] == ["NVIDIA RTX"]


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")


def test_hwmon_reads_amdgpu_with_junction_preferred(tmp_path):
    # Real sysfs makes cardN/device a symlink to the PCI device; the driver resolves it with realpath, which works
    # the same on a plain directory, so the fake tree needs no symlink (and runs on Windows too).
    dev = tmp_path / "drm" / "card1" / "device"
    for f, v in {"vendor": "0x1002", "device": "0x744c", "gpu_busy_percent": "97",
                 "mem_info_vram_used": str(8 * 2 ** 30)}.items():
        _write(dev / f, v + "\n")
    hw = dev / "hwmon" / "hwmon4"
    for f, v in {"name": "amdgpu", "temp1_input": "61000", "temp1_label": "edge", "temp2_input": "78000",
                 "temp2_label": "junction", "power1_average": "287000000", "fan1_input": "1650"}.items():
        _write(hw / f, v + "\n")
    (tmp_path / "drm" / "card1-DP-1").mkdir()                 # connector entries are skipped
    devs = hwmon.devices(root=str(tmp_path / "drm"))
    assert [(n, ids) for n, ids, _ in devs] == [("amdgpu 1002:744c (card1)", (0x1002, 0x744C))]
    r = devs[0][2]().read()
    assert (r["temp_c"], r["power_w"], r["fan_rpm"], r["util_pct"], r["mem_used_mb"]) == (78.0, 287.0, 1650.0, 97.0, 8192.0)


def test_hwmon_energy_counter_becomes_watts(tmp_path):
    hw = tmp_path / "hw"
    _write(hw / "energy1_input", "1000000\n")
    _write(hw / "temp1_input", "50000\n")
    clock = iter([10.0, 12.0])
    d = hwmon.HwmonDevice(str(tmp_path), str(hw), "xe", clock=lambda: next(clock))
    assert d.read().get("power_w") is None
    _write(hw / "energy1_input", "61000000\n")               # +60 J in 2 s
    assert d.read()["power_w"] == 30.0


# ---- real hardware, where present ----

def test_live_sources_smoke_on_this_machine():
    found = []
    for mod in (wddm, igcl, levelzero, nvml, hwmon):
        try:
            found += [(mod.__name__, n) for n, _, _ in mod.devices()]
        except OSError:
            continue
    if not found:
        pytest.skip("no real GPU telemetry source on this machine")
    sources, report = discover(match=found[0][1])
    for s in sources:
        r = s.read()
        assert isinstance(r, dict) and set(r) <= set(GPU_TELEMETRY_KEYS) | {"extra"}
        s.close()
