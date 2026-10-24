"""SPEC-1 Snapshot State Serialization Engine."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("spec1.engine.tools.snapshot_manager")

class SnapshotManager:
    def __init__(self, data_dir: str = "src/spec1_engine/data"):
        self.data_dir = Path(data_dir)
        self.active_file = self.data_dir / "portland_snapshot_base.json"
        self.vault_dir = self.data_dir / "vault"

        # Ensure system storage boundaries exist
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def calculate_checksum(self, data: Dict[str, Any]) -> str:
        """Generates a deterministic SHA-256 footprint of the dataset state."""
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def freeze_active_state(self, milestone_name: str) -> str:
        """Serializes, cryptographically hashes, and commits the active state to the vault."""
        if not self.active_file.exists():
            logger.error("EXECUTION_FAILED: Active snapshot matrix target does not exist.")
            return "ERROR_MISSING_TARGET"

        try:
            with open(self.active_file, "r") as f:
                payload = json.load(f)
        except Exception as err:
            logger.error(f"PARSING_FAILED: Staged JSON matrix corrupted: {err}")
            return "ERROR_CORRUPT_JSON"

        # Inject runtime verification metadata
        timestamp = datetime.now(timezone.utc).isoformat()
        checksum = self.calculate_checksum(payload)

        payload["snapshot_metadata"]["frozen_at"] = timestamp
        payload["snapshot_metadata"]["checksum"] = checksum
        payload["snapshot_metadata"]["milestone_tag"] = milestone_name.upper()

        # Build clean chronological index filename
        safe_name = milestone_name.lower().replace(" ", "_")
        datestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_filename = f"snapshot_{datestamp}_{safe_name}.json"
        archive_path = self.vault_dir / archive_filename

        # Write immutable archive snapshot frame
        with open(archive_path, "w") as f:
            json.dump(payload, f, indent=4)

        logger.info(f"SNAPSHOT_SECURED // HASH:{checksum[:12]} // DEST:{archive_path.name}")
        print(f"[SUCCESS] SPEC-1 STATE FROZEN: {archive_filename}")
        print(f"--> CHECKSUM: {checksum}")

        return checksum

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    manager = SnapshotManager()
    tag = sys.argv[1] if len(sys.argv) > 1 else "MANUAL_MILESTONE"
    manager.freeze_active_state(tag)
