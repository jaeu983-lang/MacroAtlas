"""Standalone bounded CSV qualification worker. No package imports or network access."""

import csv
import hashlib
import io
import json
import os
import stat
import sys
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path, PurePosixPath


class StopTrial(Exception):
    pass


def run(job):
    import resource

    limits = job["limits"]
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory_bytes"], limits["memory_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_seconds"], limits["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["output_bytes"], limits["output_bytes"]))
    started = time.monotonic()
    path = Path(job["path"])
    with ExitStack() as stack:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        source = stack.enter_context(os.fdopen(descriptor, "rb"))
        initial = os.fstat(source.fileno())
        expected = job.get("source_stat")
        if expected is not None and any(getattr(initial, k) != v for k, v in expected.items()):
            raise StopTrial("source_changed_since_binding")
        if not stat.S_ISREG(initial.st_mode) or initial.st_size >= limits["input_bytes"]:
            raise StopTrial("input_budget")

        def source_hash():
            source.seek(0)
            digest, size = hashlib.sha256(), 0
            while chunk := source.read(65536):
                size += len(chunk)
                if size >= limits["input_bytes"]:
                    raise StopTrial("input_budget")
                digest.update(chunk)
            source.seek(0)
            return digest.hexdigest()

        digest = source_hash()
        stream = source
        suffix = path.suffix.lower()
        if suffix == ".zip":
            archive = stack.enter_context(zipfile.ZipFile(source))
            entries = archive.infolist()
            if len(entries) >= 1000 or sum(i.file_size for i in entries) >= 256 * 1024 * 1024:
                raise StopTrial("archive_budget")
            names = set()
            for item in entries:
                name = item.filename
                if (
                    name in names
                    or "\\" in name
                    or name.startswith("/")
                    or ".." in PurePosixPath(name).parts
                    or ":" in name
                    or item.flag_bits & 1
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise StopTrial("archive_security")
                names.add(name)
                if item.file_size / max(1, item.compress_size) >= 200:
                    raise StopTrial("archive_ratio")
            members = [
                i
                for i in entries
                if not i.is_dir()
                and PurePosixPath(i.filename).suffix.lower() in {".csv", ".tsv", ".txt"}
            ]
            selected = job["scope"].get("zip_member")
            if selected is not None:
                members = [i for i in members if i.filename == selected]
            if len(members) != 1:
                raise StopTrial("ambiguous_archive")
            if members[0].file_size >= limits["input_bytes"]:
                raise StopTrial("member_budget")
            stream = stack.enter_context(archive.open(members[0]))
            suffix = PurePosixPath(members[0].filename).suffix.lower()
        if suffix not in {".csv", ".tsv", ".txt"}:
            raise StopTrial("unsupported_format")
        # A limited line reader bounds malformed huge lines before csv allocates fields.
        text = stack.enter_context(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
        consumed = 0

        def lines():
            nonlocal consumed
            while line := text.readline(2 * 1024 * 1024):
                if len(line) >= 2 * 1024 * 1024:
                    raise StopTrial("line_budget")
                consumed += len(line.encode("utf-8"))
                if consumed >= limits["input_bytes"]:
                    raise StopTrial("decoded_input_budget")
                yield line

        iterator = lines()
        first = next(iterator, "")
        delimiter = job["scope"].get("delimiter")
        inferred = False
        if delimiter is None:
            if suffix in {".csv", ".tsv"}:
                delimiter = "," if suffix == ".csv" else "\t"
            else:
                delimiter = csv.Sniffer().sniff(first[:65536], delimiters=",\t;|").delimiter
                inferred = True
        if delimiter not in {",", "\t", ";", "|"}:
            raise StopTrial("unsupported_delimiter")
        from itertools import chain

        csv.field_size_limit(1024 * 1024)
        reader = csv.reader(chain((first,), iterator), delimiter=delimiter, strict=True)
        header_row = job["scope"].get("header_row", 1)
        if type(header_row) is not int or not 1 <= header_row <= 100:
            raise StopTrial("header_scope")
        header = []
        for _ in range(header_row):
            header = next(reader, [])
        if not header or len(header) > 4096 or any(not h.strip() for h in header):
            raise StopTrial("header_invalid")
        if len(set(header)) != len(header):
            raise StopTrial("duplicate_header")
        rows, empty, zero, output_bytes, chunks = 0, 0, 0, 0, 0
        output_digest = hashlib.sha256()
        output = None
        try:
            for row in reader:
                if len(row) != len(header):
                    raise StopTrial("ragged_rows")
                rows += 1
                if rows > 2_000_000:
                    raise StopTrial("row_budget")
                encoded = (
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode()
                output_bytes += len(encoded)
                if output_bytes >= limits["output_bytes"]:
                    raise StopTrial("output_budget")
                if (rows - 1) % 10000 == 0:
                    if output:
                        output.close()
                    chunks += 1
                    output = (Path(job["scratch"]) / f"chunk-{chunks:04d}.jsonl").open("xb")
                output.write(encoded)
                output_digest.update(encoded)
                empty += sum(value == "" for value in row)
                zero += sum(value == "0" for value in row)
        finally:
            if output:
                output.close()
        if not rows:
            raise StopTrial("no_observations")
        if digest != source_hash() or initial.st_mtime_ns != os.fstat(source.fileno()).st_mtime_ns:
            raise StopTrial("source_changed_during_trial")
        return {
            "trial_state": "PASSED",
            "rows": rows,
            "columns": len(header),
            "empty_fields": empty,
            "zero_fields": zero,
            "chunks": chunks,
            "output_bytes": output_bytes,
            "output_sha256": output_digest.hexdigest(),
            "raw_sha256": digest,
            "delimiter_inferred": inferred,
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        }


if __name__ == "__main__":
    try:
        job = json.loads(Path(sys.argv[1]).read_text())
        result = run(job)
    except StopTrial as error:
        result = {"trial_state": "REJECTED", "reason": str(error)}
    except MemoryError:
        result = {"trial_state": "REJECTED", "reason": "memory_budget"}
    except Exception:  # noqa: BLE001 - never expose source values or library diagnostics
        result = {"trial_state": "REJECTED", "reason": "format_or_worker_error"}
    print(json.dumps(result))
