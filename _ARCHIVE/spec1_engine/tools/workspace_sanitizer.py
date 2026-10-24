"""SPEC-1 Workspace Sanitation and Redundancy Elimination Engine."""
import shutil
from pathlib import Path

class WorkspaceSanitizer:
    def __init__(self, root_dir: str = "."):
        self.root = Path(root_dir)
        self.core_data_hub = self.root / "src/spec1_engine/data"

        # Exact explicit root files to target for eviction
        self.trash_files = [
            't"', '${HOME}', 'spec1_intelligence.jsonl',
            'spec1_batch_builder.py', 'spec1_report_generator.py',
            'patch_routes.py', 'patch_spatial_route.py', 'patch_canvas_layer.py'
        ]

        # Volatile folders to strip down to ensure clean compilation loops
        self.purge_folders = [
            self.root / "output",
            self.root / "generated/reports"
        ]

    def purge_root_litter(self):
        """Scrubs malformed characters and redundant script duplicates from project root."""
        print("// SPEC-1 // Initiating Workspace Sanitation Sequence...")

        # 1. Clean explicit trash names
        for filename in self.trash_files:
            target = self.root / filename
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                print(f"  [EVICTED] Redundant Root Target: {filename}")

        # 2. Sweep orphan loose documents from the root context
        for item in self.root.glob("*.html"):
            item.unlink()
            print(f"  [PURGED] Loose HTML Artifact: {item.name}")

        for item in self.root.glob("*.pdf"):
            item.unlink()
            print(f"  [PURGED] Loose PDF Artifact: {item.name}")

    def purge_volatile_output_caches(self):
        """Wipes out volatile build artifacts to allow clean, unfragmented generation runs."""
        for folder in self.purge_folders:
            if folder.exists():
                shutil.rmtree(folder)
                folder.mkdir(parents=True, exist_ok=True)
                print(f"  [FLUSHED] System Cache Area: {folder.relative_to(self.root)}")

    def enforce_integrity(self):
        """Verifies that the consolidated core data matrix remains untouched and secure."""
        print("// SPEC-1 // Running Structural Integrity Verification...")
        critical_paths = [
            self.core_data_hub / "spatial/portland_transit_corridors.geojson",
            self.core_data_hub / "signals/psyop_signals.jsonl",
            self.core_data_hub / "portland_snapshot_base.json",
            self.core_data_hub / "spec1_intelligence.jsonl"
        ]

        healthy = True
        for path in critical_paths:
            if path.exists():
                print(f"  [SECURE] Core Telemetry Node Online: {path.relative_to(self.root)}")
            else:
                print(f"  [WARNING] Missing Expected Data Node: {path.name}")
                healthy = False

        if healthy:
            print("[SUCCESS] SPEC-1 Data Infrastructure Is Streamlined & Vertically Integrated.")

if __name__ == "__main__":
    sanitizer = WorkspaceSanitizer()
    sanitizer.purge_root_litter()
    sanitizer.purge_volatile_output_caches()
    sanitizer.enforce_integrity()
