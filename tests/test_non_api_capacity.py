import tempfile
from pathlib import Path
from unittest.mock import patch

from macro_data_platform.config import Settings
from macro_data_platform.ingestion.non_api_capacity import (
    MAX_INPUT_BYTES,
    DeferredNonAPIStore,
    decision,
    inspect_bytes,
    inspect_file,
)


def test_large_local_file_is_not_opened():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'large.csv'
        with path.open('wb') as stream:
            stream.truncate(MAX_INPUT_BYTES)
        with patch.object(Path, 'open', side_effect=AssertionError('must not read')):
            assert inspect_file(path, 'csv', {})['reason'] == 'input_bytes'


def test_exact_column_boundary_defers_but_smaller_table_passes():
    assert inspect_bytes(b'a,b\n1,2\n', 'csv', {}) is None
    raw = (','.join(f'c{i}' for i in range(1000)) + '\n').encode()
    assert inspect_bytes(raw, 'csv', {})['reason'] == 'columns'


def test_deduplicated_records_keep_history_across_restart():
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(Path(directory))
        scope = {'relative_path': 'data/inbox/a.csv', 'format': 'csv'}
        first = DeferredNonAPIStore(settings).register(scope, 'task1', 's', decision('rows', 100000))
        second = DeferredNonAPIStore(settings).register(scope, 'task2', 's', decision('rows', 100001))
        restarted = DeferredNonAPIStore(settings)
        assert first['id'] == second['id']
        assert len(restarted.list()) == 1
        assert len(restarted.list(first['id'])) == 2
