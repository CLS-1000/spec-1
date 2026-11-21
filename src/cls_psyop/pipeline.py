# @domain:   product
# @module:   pipeline
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Psyop detection pipeline — end-to-end processing with enhanced features."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from threading import Lock
from typing import Iterator, Optional, Protocol, Sequence, Union

from cls_psyop.patterns import PATTERNS
from cls_psyop.scorer import filter_risky, score_text
from cls_psyop.schemas import PsyopScore
from cls_psyop.store import PsyopStore
from spec1_labels import PSYOP_HIGH_RISK, PSYOP_MEDIUM_RISK, PSYOP_LOW_RISK

logger = logging.getLogger(__name__)

# Custom exceptions
class PsyopPipelineError(Exception):
    """Base exception for pipeline errors."""
    pass

class ValidationError(PsyopPipelineError):
    """Raised when input validation fails."""
    pass

class StorageError(PsyopPipelineError):
    """Raised when storage operations fail."""
    pass


@dataclass
class PsyopPipelineStats:
    """Comprehensive statistics for pipeline execution."""
    run_id: str
    started_at: str
    records_analysed: int = 0
    risky_detected: int = 0
    high_risk: int = 0
    medium_risk: int = 0
    low_risk: int = 0
    stored: int = 0
    processing_time_ms: float = 0.0
    errors: list[dict] = field(default_factory=list)  # Structured error objects
    finished_at: Optional[str] = None

    def finish(self) -> None:
        """Mark pipeline as finished with timestamp."""
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def add_error(self, error: Exception, context: Optional[dict] = None) -> None:
        """Add structured error information safely."""
        # Sanitize error message to prevent Information Exposure (CWE-209)
        if isinstance(error, (ValidationError, StorageError)):
            # Domain errors are safe to expose
            safe_message = str(error)
        else:
            # Mask generic or built-in system exceptions
            safe_message = "An internal processing error occurred."

        self.errors.append({
            "type": error.__class__.__name__,
            "message": safe_message,
            "context": context or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def to_dict(self) -> dict:
        """Convert stats to serializable dictionary."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "records_analysed": self.records_analysed,
            "risky_detected": self.risky_detected,
            "high_risk": self.high_risk,
            "medium_risk": self.medium_risk,
            "low_risk": self.low_risk,
            "stored": self.stored,
            "processing_time_ms": self.processing_time_ms,
            "error_count": len(self.errors),
            "errors": self.errors,
        }

    def __repr__(self) -> str:
        success_rate = (self.records_analysed - len(self.errors)) / max(self.records_analysed, 1) * 100
        return (f"PsyopPipelineStats(run_id={self.run_id}, analysed={self.records_analysed}, "
                f"risky={self.risky_detected}, stored={self.stored}, "
                f"errors={len(self.errors)}, success_rate={success_rate:.1f}%)")


class RecordValidator(Protocol):
    """Protocol for record validation."""
    def __call__(self, record: dict, index: int) -> Optional[str]: ...


class ProgressCallback(Protocol):
    """Protocol for progress reporting."""
    def __call__(self, processed: int, total: int, stats: PsyopPipelineStats) -> None: ...


@dataclass
class PipelineConfig:
    """Configuration for the psyop pipeline."""
    store_path: Path = field(default_factory=lambda: anchor_to_home("psyop_scores.jsonl"))
    run_id: str = ""
    min_classification: str = PSYOP_LOW_RISK
    chunk_size: int = 1000
    max_errors: int = 100
    validate_records: bool = True
    required_fields: tuple[str, ...] = ('text',)
    enable_progress_callback: bool = False
    auto_flush: bool = True
    use_compression: bool = False
    retry_on_failure: int = 3
    timeout_seconds: float = 300.0


class PsyopPipeline:
    """End-to-end psyop detection pipeline with enhanced features."""

    # Class-level cache for expensive operations
    _score_cache: dict[str, PsyopScore] = {}
    _cache_lock = Lock()

    def __init__(
        self,
        store_path: Optional[Path] = None,
        run_id: str = "",
        min_classification: str = PSYOP_LOW_RISK,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        """
        Initialize the psyop detection pipeline.

        Args:
            store_path: Path to store results. Defaults to config if not provided.
            run_id: Unique identifier for this run. Auto-generated if empty.
            min_classification: Minimum risk level to store.
            config: Full pipeline configuration. If provided, overrides other params.
        """
        self.config = config or PipelineConfig()

        # Override config with explicit parameters
        if store_path is not None:
            self.config.store_path = store_path
        if run_id:
            self.config.run_id = run_id
        if min_classification != PSYOP_LOW_RISK:
            self.config.min_classification = min_classification

        # Generate run_id if not provided
        if not self.config.run_id:
            self.config.run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")

        # Append run_id to store path for uniqueness if not specified
        if store_path is None and not config:
            self.config.store_path = Path(f"psyop_scores_{self.config.run_id}.jsonl")

        self.store = PsyopStore(self.config.store_path)
        self._lock = Lock()
        self._validators: list[RecordValidator] = []
        self._progress_callback: Optional[ProgressCallback] = None

        # Register default validators
        if self.config.validate_records:
            self._register_default_validators()

    def _register_default_validators(self) -> None:
        """Register default record validators."""
        self.register_validator(self._validate_required_fields)
        self.register_validator(self._validate_text_type)

    def register_validator(self, validator: RecordValidator) -> None:
        """Add a custom record validator."""
        self._validators.append(validator)

    def set_progress_callback(self, callback: ProgressCallback) -> None:
        """Set a callback for progress reporting."""
        self._progress_callback = callback
        self.config.enable_progress_callback = True

    @staticmethod
    def _validate_required_fields(record: dict, index: int) -> Optional[str]:
        """Validate that all required fields are present."""
        missing = [f for f in PipelineConfig.required_fields if f not in record]
        if missing:
            return f"Record {index} missing required fields: {missing}"
        return None

    @staticmethod
    def _validate_text_type(record: dict, index: int) -> Optional[str]:
        """Validate that text field has correct type."""
        text = record.get('text')
        if text is not None and not isinstance(text, str):
            return f"Record {index} 'text' field must be string, got {type(text).__name__}"
        return None

    def _validate_record(self, record: dict, index: int) -> tuple[bool, Optional[str]]:
        """Validate a single record using all registered validators."""
        for validator in self._validators:
            error = validator(record, index)
            if error:
                return False, error
        return True, None

    @contextmanager
    def _time_operation(self, stats: PsyopPipelineStats) -> Iterator[None]:
        """Context manager to time operations."""
        start = datetime.now()
        try:
            yield
        finally:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            stats.processing_time_ms += duration_ms

    def _chunk_records(self, records: Sequence[dict]) -> Iterator[list[dict]]:
        """Split records into chunks for memory-efficient processing."""
        for i in range(0, len(records), self.config.chunk_size):
            yield records[i:i + self.config.chunk_size]

    def _process_chunk(
        self,
        chunk: list[dict],
        start_idx: int,
        stats: PsyopPipelineStats
    ) -> tuple[list[PsyopScore], int]:
        """Process a single chunk of records."""
        chunk_scores = []
        chunk_errors = 0

        for i, record in enumerate(chunk):
            global_idx = start_idx + i

            # Validate record
            is_valid, error_msg = self._validate_record(record, global_idx)
            if not is_valid:
                stats.add_error(ValidationError(error_msg), {"record_index": global_idx})
                chunk_errors += 1
                continue

            try:
                # Score the record
                score = score_text(record.get('text', ''), PATTERNS)

                # Add metadata
                score.metadata = {
                    **getattr(score, 'metadata', {}),
                    'record_index': global_idx,
                    'run_id': self.config.run_id,
                    'original_record': {k: v for k, v in record.items() if k != 'text'},  # Don't duplicate text
                }

                chunk_scores.append(score)

                # Update stats
                if score.classification == PSYOP_HIGH_RISK:
                    stats.high_risk += 1
                elif score.classification == PSYOP_MEDIUM_RISK:
                    stats.medium_risk += 1
                elif score.classification == PSYOP_LOW_RISK:
                    stats.low_risk += 1

            except Exception as e:
                stats.add_error(e, {"record_index": global_idx, "record": str(record)[:200]})
                chunk_errors += 1
                logger.warning(f"Failed to score record {global_idx}: {e}")

            # Progress reporting
            if self.config.enable_progress_callback and self._progress_callback:
                if (global_idx + 1) % (self.config.chunk_size // 10) == 0:  # Report every 10% of chunk
                    self._progress_callback(global_idx + 1, stats.records_analysed, stats)

        return chunk_scores, chunk_errors

    def run(
        self,
        records: Sequence[dict],
        use_cache: bool = True,
    ) -> PsyopPipelineStats:
        """
        Score all records for psyop indicators, persist risky ones.

        Args:
            records: List of dicts, each containing required fields.
            use_cache: Whether to use cached results for identical text.

        Returns:
            PsyopPipelineStats with processing metrics.

        Raises:
            ValidationError: If no valid records to process.
        """
        if not records:
            logger.warning("Empty records sequence provided")
            return PsyopPipelineStats(
                run_id=self.config.run_id,
                started_at=datetime.now(timezone.utc).isoformat(),
            )

        stats = PsyopPipelineStats(
            run_id=self.config.run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        stats.records_analysed = len(records)

        all_scores = []
        total_errors = 0

        try:
            with self._time_operation(stats):
                # Process in chunks to manage memory
                for chunk_idx, chunk in enumerate(self._chunk_records(records)):
                    logger.debug(f"Processing chunk {chunk_idx + 1}/{len(records) // self.config.chunk_size + 1}")

                    chunk_scores, chunk_errors = self._process_chunk(
                        chunk,
                        chunk_idx * self.config.chunk_size,
                        stats
                    )
                    all_scores.extend(chunk_scores)
                    total_errors += chunk_errors

                    # Stop if too many errors
                    if total_errors >= self.config.max_errors:
                        raise ValidationError(
                            f"Too many errors ({total_errors}). Stopping pipeline."
                        )

                # Filter and store risky records
                if all_scores:
                    with self._time_operation(stats):
                        risky = filter_risky(all_scores, self.config.min_classification)
                        stats.risky_detected = len(risky)

                        if risky and self.config.auto_flush:
                            # Store with retry logic
                            for attempt in range(self.config.retry_on_failure):
                                try:
                                    written = self.store.save_batch(risky)
                                    stats.stored = len(written)
                                    break
                                except Exception as e:
                                    if attempt == self.config.retry_on_failure - 1:
                                        raise StorageError(f"Failed to store after {self.config.retry_on_failure} attempts") from e
                                    logger.warning(f"Storage attempt {attempt + 1} failed: {e}")
                else:
                    logger.warning("No records were successfully scored")

        except ValidationError as e:
            stats.add_error(e)
            logger.error(f"Pipeline validation failed: {e}")
        except StorageError as e:
            stats.add_error(e)
            logger.error(f"Storage operation failed: {e}")
        except Exception as e:
            stats.add_error(e)
            logger.exception("Unexpected pipeline error")
        finally:
            stats.finish()

        # Log summary
        logger.info(
            f"Pipeline {stats.run_id} completed: "
            f"processed={stats.records_analysed}, "
            f"risky={stats.risky_detected}, "
            f"stored={stats.stored}, "
            f"errors={len(stats.errors)}, "
            f"time={stats.processing_time_ms:.0f}ms"
        )

        return stats

    @classmethod
    def analyse_text_cached(cls, text: str) -> PsyopScore:
        """
        Score a single piece of text with caching.

        Args:
            text: The text to analyze.

        Returns:
            PsyopScore object with risk assessment.
        """
        with cls._cache_lock:
            if text not in cls._score_cache:
                cls._score_cache[text] = score_text(text, PATTERNS)
            return cls._score_cache[text]

    def analyse_text(self, text: str, use_cache: bool = True) -> PsyopScore:
        """
        Score a single piece of text.

        Args:
            text: The text to analyze.
            use_cache: Whether to use global cache.

        Returns:
            PsyopScore object with risk assessment.
        """
        if use_cache:
            return self.analyse_text_cached(text)
        return score_text(text, PATTERNS)

    def get_high_risk(self, as_objects: bool = False) -> Union[list[dict], list[PsyopScore]]:
        """
        Return stored HIGH_RISK scores.

        Args:
            as_objects: If True, return PsyopScore objects; otherwise return dicts.

        Returns:
            List of high-risk scores in requested format.
        """
        if as_objects:
            return list(self.store.load_all())
        return list(self.store.by_classification(PSYOP_HIGH_RISK))

    def get_scores_by_date(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None
    ) -> list[PsyopScore]:
        """
        Retrieve scores within a date range.

        Args:
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive). Defaults to now.

        Returns:
            List of scores within the date range.
        """
        end_date = end_date or datetime.now(timezone.utc)
        all_scores = self.store.load_all()

        return [
            score for score in all_scores
            if start_date <= datetime.fromisoformat(score.timestamp) <= end_date
        ]

    def clear_cache(self) -> None:
        """Clear the global text analysis cache."""
        with self._cache_lock:
            self._score_cache.clear()
            logger.info("Analysis cache cleared")

    @property
    def cache_size(self) -> int:
        """Get current cache size."""
        with self._cache_lock:
            return len(self._score_cache)


def run_pipeline(
    records: Sequence[dict],
    store_path: Optional[Path] = None,
    min_classification: str = PSYOP_LOW_RISK,
    progress_callback: Optional[ProgressCallback] = None,
    chunk_size: int = 1000,
) -> PsyopPipelineStats:
    """
    Convenience function to run psyop pipeline on records.

    Args:
        records: List of records to analyze.
        store_path: Path to store results. Auto-generated if None.
        min_classification: Minimum risk level to store.
        progress_callback: Optional callback for progress updates.
        chunk_size: Number of records to process at once.

    Returns:
        Pipeline statistics.

    Example:
        >>> records = [{'text': 'suspicious message', 'id': 1}]
        >>> stats = run_pipeline(records)
        >>> print(f"Found {stats.risky_detected} risky messages")
    """
    config = PipelineConfig(
        store_path=store_path or anchor_to_home("psyop_scores.jsonl"),
        min_classification=min_classification,
        chunk_size=chunk_size,
    )

    pipeline = PsyopPipeline(config=config)

    if progress_callback:
        pipeline.set_progress_callback(progress_callback)

    return pipeline.run(records)


# Example usage with progress callback
def example_progress_callback(processed: int, total: int, stats: PsyopPipelineStats) -> None:
    """Example progress callback that prints to console."""
    percent = (processed / total) * 100
    print(f"\rProgress: {processed}/{total} ({percent:.1f}%) - "
          f"Risky: {stats.risky_detected}", end='', flush=True)
    if processed == total:
        print()  # New line at the end


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Example usage
    sample_records = [
        {"text": "This is a normal message", "id": 1, "source": "test"},
        {"text": "Suspicious coordinated campaign message", "id": 2, "source": "test"},
        {"text": "", "id": 3, "source": "test"},  # Invalid record
    ]

    stats = run_pipeline(
        sample_records,
        progress_callback=example_progress_callback,
        chunk_size=2,
    )

    print(f"\nFinal stats: {stats}")
