"""Deprecated wrapper module.

Use `tuner_local` and `tuner_cloud` directly. This file remains only to
provide backward-compatible re-exports and thin wrappers.
"""

from tuner_local import run_tuning_session as _local_run_tuning_session
from tuner_cloud import run_cloud_tuning_session as _cloud_run_tuning_session


def run_cloud_tuning_session(
    storage_dir: str = None, count: int = 500, batch_size: int = 50, model: str = None
):
    """Thin wrapper calling tuner_cloud.run_cloud_tuning_session."""
    return _cloud_run_tuning_session(
        storage_dir, count=count, batch_size=batch_size, model=model
    )


def run_tuning_session(storage_dir: str = None, count: int = 50):
    """Thin wrapper calling tuner_local.run_tuning_session."""
    return _local_run_tuning_session(storage_dir, count=count)
