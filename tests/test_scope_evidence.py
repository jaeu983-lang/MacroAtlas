"""Bounded provenance checks for the BIS flat file scope adapter."""
import hashlib
import io
import json
import zipfile

from macro_data_platform.analysis.scope_evidence import (
    BIS_FLAT_AGENCY,
    BIS_FLAT_DATASET,
    BIS_FLAT_URL,
    resolve_bis_flat_scope,
)


def _save_capture(root, package_id, content):
    package = root / "data" / "raw" / "tabular" / package_id
    package.mkdir(parents=True)
    raw = package / "source.zip"
    raw.write_bytes(content)
    manifest = package / "request.json"
    manifest.write_text(json.dumps({
        "package_id": package_id,
        "request_context": {
            "source_url": BIS_FLAT_URL,
            "source_http_status": 200,
            "source_agency": BIS_FLAT_AGENCY,
            "source_captured_at": "2026-10-26T09:18:10.929482+00:00",
            "format": "zip",
        },
        "raw": {
            "path": f"data/raw/tabular/{package_id}/source.zip",
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        },
    }), encoding="utf-8")
    return raw, manifest


def _archive_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("WS_GLI_csv_flat.csv", "TIME_PERIOD,OBS_VALUE\n2026,1\n")
    return output.getvalue()


def test_bis_scope_requires_exact_manifest_and_matching_raw_hash(tmp_path):
    content = _archive_bytes()
    raw, manifest = _save_capture(tmp_path, "a" * 32, content)

    resolved = resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path="data/raw/tabular/" + "a" * 32 + "/source.zip",
        request_manifest_path="data/raw/tabular/" + "a" * 32 + "/request.json",
    )

    assert resolved["institution_id"] == "bis"
    assert resolved["dataset_id"] == BIS_FLAT_DATASET
    assert resolved["source_evidence"]["request_manifest_path"] == manifest.relative_to(
        tmp_path,
    ).as_posix()
    assert resolved["source_evidence"]["raw_sha256"] == hashlib.sha256(content).hexdigest()
    assert resolve_bis_flat_scope(
        tmp_path, "data", source_url="https://data.bis.org/other.zip",
        source_agency=BIS_FLAT_AGENCY,
        source_raw_path=raw.relative_to(tmp_path).as_posix(),
        request_manifest_path=manifest.relative_to(tmp_path).as_posix(),
    ) is None
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["request_context"]["source_url"] = "https://data.bis.org/other.zip"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    assert resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path=raw.relative_to(tmp_path).as_posix(),
        request_manifest_path=manifest.relative_to(tmp_path).as_posix(),
    ) is None
    document["request_context"]["source_url"] = BIS_FLAT_URL
    document["request_context"]["source_agency"] = "Unverified Agency"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    assert resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path=raw.relative_to(tmp_path).as_posix(),
        request_manifest_path=manifest.relative_to(tmp_path).as_posix(),
    ) is None
    document["request_context"]["source_agency"] = BIS_FLAT_AGENCY
    manifest.write_text(json.dumps(document), encoding="utf-8")
    assert resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path="data/raw/tabular/../source.zip",
        request_manifest_path=manifest.relative_to(tmp_path).as_posix(),
    ) is None

    raw.write_bytes(b"modified bytes")
    assert resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path=raw.relative_to(tmp_path).as_posix(),
        request_manifest_path=manifest.relative_to(tmp_path).as_posix(),
    ) is None


def test_bis_scope_can_link_inbox_copy_only_to_matching_saved_capture(tmp_path):
    content = _archive_bytes()
    _save_capture(tmp_path, "b" * 32, content)
    inbox = tmp_path / "data" / "inbox"
    inbox.mkdir(parents=True)
    candidate = inbox / "candidate.zip"
    candidate.write_bytes(content)

    resolved = resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path="data/inbox/candidate.zip", request_manifest_path=None,
    )

    assert resolved["dataset_id"] == BIS_FLAT_DATASET
    assert resolved["source_evidence"]["raw_path"] == (
        "data/raw/tabular/" + "b" * 32 + "/source.zip"
    )

    candidate.write_bytes(b"different file")
    assert resolve_bis_flat_scope(
        tmp_path, "data", source_url=BIS_FLAT_URL, source_agency=BIS_FLAT_AGENCY,
        source_raw_path="data/inbox/candidate.zip", request_manifest_path=None,
    ) is None
