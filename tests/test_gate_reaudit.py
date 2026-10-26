"""Current-code regression checks for capacity routing and gate boundaries."""
import io
import json
import zipfile
from unittest.mock import Mock

import pytest

from macro_data_platform.cli import build_parser, dispatch
from macro_data_platform.config import Settings
from macro_data_platform.connectors import official_files
from macro_data_platform.connectors.official_files import FileCapacityFailure, OfficialFileTransport
from macro_data_platform.contracts import StageStatus
from macro_data_platform.ingestion import non_api_capacity as capacity
from macro_data_platform.ingestion.gate_c_watch import (
    build_gate_c_watch_plan,
    make_gate_c_watch_orchestrator,
)
from macro_data_platform.ingestion.tabular_files import TabularFileEngine
from macro_data_platform.orchestration import StageInput
from macro_data_platform.storage.history import HistoryStore


def zip_body(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_zip_readme_does_not_block_valid_table(tmp_path):
    settings = Settings(tmp_path)
    source = tmp_path / 'data/inbox/source.zip'
    source.parent.mkdir(parents=True)
    source.write_bytes(zip_body({'readme.md': 'Official notes', 'data.csv': 'year,value\n2020,1\n'}))
    result = TabularFileEngine(settings).run(StageInput('t', 'read', 's', {
        'relative_path': 'data/inbox/source.zip', 'format': 'zip',
    }, None, ()))
    assert result.status == StageStatus.SUCCEEDED


@pytest.mark.parametrize('rows,columns,cells', [(3, 1000, 500000), (100000, 2, 500000),
                                               (100000, 1000, 6)])
def test_exact_table_boundaries_and_below(monkeypatch, rows, columns, cells):
    monkeypatch.setattr(capacity, 'MAX_ROWS', rows)
    monkeypatch.setattr(capacity, 'MAX_COLUMNS', columns)
    monkeypatch.setattr(capacity, 'MAX_CELLS', cells)
    body = b'a,b\n1,2\n3,4\n5,6\n'
    assert capacity.inspect_bytes(body, 'csv', {}) is not None
    assert capacity.inspect_bytes(b'a\n1\n', 'csv', {}) is None


@pytest.mark.parametrize('limit', ['MAX_ZIP_ENTRIES', 'MAX_ZIP_UNCOMPRESSED_BYTES', 'MAX_INPUT_BYTES'])
def test_zip_header_limits_stop_before_member_read(monkeypatch, limit):
    body = zip_body({'data.csv': 'a,b\n1,2\n'})
    monkeypatch.setattr(capacity, limit, 1 if limit == 'MAX_ZIP_ENTRIES' else 8)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(zipfile.ZipFile, 'open', Mock(side_effect=AssertionError('must not unpack')))
        assert capacity.inspect_bytes(body, 'zip', {})['status'] == 'deferred'


def test_corrupt_xls_is_reviewed_not_unhandled():
    assert capacity.inspect_bytes(b'not an XLS workbook', 'xls', {})['status'] == 'inspection_required'


def test_read_only_cli_creates_no_storage(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
    args = build_parser().parse_args(['--project-root', str(tmp_path), 'deferred'])
    assert dispatch(args) == (0, {'records': []})
    assert not (tmp_path / 'data').exists()


def test_deferred_event_cli_includes_immutable_sequence_number(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
    settings = Settings(tmp_path)
    record = capacity.DeferredNonAPIStore(settings).register(
        {'relative_path': 'data/inbox/a.csv'}, 'origin-task', 'inspect',
        capacity.decision('cells', 500001, 500000),
    )
    args = build_parser().parse_args([
        '--project-root', str(tmp_path), 'deferred', record['id'], '--events',
    ])
    status, result = dispatch(args)
    assert status == 0
    assert result['events'][0]['event_seq'] == 1
    assert result['events'][0]['id'] == record['id']


def test_store_rejects_secret_url_and_returns_latest_first(tmp_path):
    store = capacity.DeferredNonAPIStore(Settings(tmp_path))
    with pytest.raises(ValueError):
        store.register({'source_url': 'https://example.org/a?token=private'}, 't', 's',
                       capacity.decision('input_bytes'))
    first = store.register({'relative_path': 'a'}, '1', 's', capacity.decision('rows'))
    store.register({'relative_path': 'b'}, '2', 's', capacity.decision('rows'))
    store.register({'relative_path': 'a'}, '3', 's', capacity.decision('rows'))
    assert store.list()[0]['id'] == first['id']
    assert len(store.list(first['id'])) == 2
    assert store.events(first['id'])[0]['event_seq'] > store.events(first['id'])[-1]['event_seq']


@pytest.mark.parametrize('header', [None, '8', '1'])
def test_transport_capacity_records_reason_and_stops_reading(monkeypatch, header):
    monkeypatch.setattr(official_files, 'MAX_FILE_BYTES', 8)
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status_code = 200
    response.headers = {} if header is None else {'Content-Length': header}
    response.iter_content.return_value = iter([b'12345678', b'should never be read'])
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.get.return_value = response
    monkeypatch.setattr(official_files.requests, 'Session', lambda: session)
    with pytest.raises(FileCapacityFailure) as caught:
        OfficialFileTransport().fetch('bis')
    assert caught.value.capacity['observed'] == 8
    if header == '8':
        response.iter_content.assert_not_called()
    assert session.get.call_count == 1


def test_download_deferral_persists_same_task_and_cli_reason(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    store = HistoryStore(settings)
    transport = Mock()
    transport.fetch.side_effect = FileCapacityFailure(16 * 1024 * 1024, 'content_length')
    runner = make_gate_c_watch_orchestrator(store, settings, transport)
    task = runner.create('capacity fixture')
    runner.plan(task.task_id, build_gate_c_watch_plan('bis'))
    result = runner.run(task.task_id)
    assert result['status'] == 'NEEDS_REVIEW'
    record = capacity.DeferredNonAPIStore(settings).list()[0]
    assert record['task_id'] == task.task_id
    assert record['reason'] == 'download_bytes'
    assert not (tmp_path / 'data/processed').exists()
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
    args = build_parser().parse_args(['--project-root', str(tmp_path), 'status', task.task_id])
    _, summary = dispatch(args)
    assert summary['non_api_deferral']['id'] == record['id']
    assert transport.fetch.call_count == 1
    json.dumps(summary)
