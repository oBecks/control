from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .found_device import FoundDevice
from .registry import MergeReport, Registry
from .scanners import SCANNERS

# Tuya only announces every ~5s, so shorter scans miss devices.
DEFAULT_TIMEOUT = 7.0


@dataclass
class ScanResult:
    devices: list[FoundDevice] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # brand -> error message

    @property
    def covered_brands(self) -> set[str]:
        return set(SCANNERS) - set(self.errors)


def run_scan(timeout: float = DEFAULT_TIMEOUT, brands: set[str] | None = None) -> ScanResult:
    """Run brand scanners in parallel. A failing brand never sinks the whole Scan."""
    scanners = {b: fn for b, fn in SCANNERS.items() if brands is None or b in brands}
    result = ScanResult()
    with ThreadPoolExecutor(max_workers=len(scanners)) as pool:
        futures = {brand: pool.submit(fn, timeout) for brand, fn in scanners.items()}
        for brand, future in futures.items():
            try:
                result.devices.extend(future.result())
            except Exception as exc:
                result.errors[brand] = f"{type(exc).__name__}: {exc}"
    # Brands not scanned this time count as not covered, same as failed ones.
    result.errors.update({b: "not scanned" for b in SCANNERS if b not in scanners})
    result.devices.sort(key=lambda d: (d.category.value, d.brand, d.ip))
    return result


def scan_and_remember(
    registry: Registry, timeout: float = DEFAULT_TIMEOUT, brands: set[str] | None = None
) -> tuple[ScanResult, MergeReport]:
    result = run_scan(timeout, brands)
    report = registry.merge_scan(result.devices, brands=result.covered_brands)
    return result, report
