"""Bounded offline SDMX structure, API catalogue and extracted sheet adapters."""
from __future__ import annotations

import json
from dataclasses import fields, replace
from xml.etree import ElementTree as ET

from macro_data_platform.discovery.institution_sites import InstitutionCandidate
from macro_data_platform.metadata.models import (
    MAX_RECORDS,
    MetadataDocument,
    MetadataRecord,
    MetadataResult,
    ScopeRelation,
    SourceAccess,
    digest,
)
from macro_data_platform.workflow_contracts import Candidate, _check
from macro_data_platform.workflow_extensions import VariantAttributes


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        _check(key not in result, "duplicate metadata JSON key")
        result[key] = value
    return result


def _load(document):
    return json.loads(document.body.decode("utf-8-sig"), object_pairs_hook=_json_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("nonfinite metadata value")))


def _labels(value, language, warnings, name):
    if isinstance(value, str):
        return value, {"und": value}
    if value is None:
        warnings.append("missing:" + name)
        return None, {}
    _check(isinstance(value, dict) and bool(value) and all(
        isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in value.items()
    ), "invalid multilingual metadata")
    key = language if language in value else min(value)
    if key != language:
        warnings.append("language_fallback:" + name + ":" + key)
    return value[key], value


def _normalize(document, dataset_id, row, path, mappings, language):
    warnings, pointers = [], {}
    _check(isinstance(row, dict), "expected series metadata row")
    label, labels = _labels(row.get("label"), language, warnings, "label")
    _check(label is not None, "series label is required")
    definition, _ = _labels(row.get("definition"), language, warnings, "definition")
    codes = {}

    def value(name):
        direct, code = row.get(name), row.get(name + "_code")
        if name in row:
            pointers[name] = path + "/" + name
        if code is not None:
            _check(isinstance(code, str) and bool(code), "expected a source code")
            codes[name] = code
            pointers[name + "_code"] = path + "/" + name + "_code"
            normalized = mappings.get(name, {}).get(code)
            pointers["mapping." + name] = "/mappings/" + name
            if normalized is None:
                warnings.append("unknown_code:" + name + ":" + code)
            if direct is not None and normalized != direct:
                warnings.append("conflict:" + name)
                return None
            return normalized
        return direct

    frequency, unit = value("frequency"), value("unit")
    variants = {f.name: value(f.name) for f in fields(VariantAttributes)
                if f.name not in {"source_codes", "frequency", "unit"}}
    variants.update(frequency=frequency, unit=unit, source_codes=codes)
    for name in ("concept_id", "label", "definition", "id", "series_key", "countries",
                 "dimensions", "available_start", "available_end", "scope", "scope_relations"):
        if name in row:
            pointers[name] = path + "/" + name
    for name in ("definition", "frequency", "unit", "available_start", "available_end"):
        if ({"definition": definition, "frequency": frequency, "unit": unit}.get(name)
                if name in {"definition", "frequency", "unit"} else row.get(name)) is None:
            warnings.append("missing:" + name)
    identity = {"institution": document.institution_id, "dataset": dataset_id,
                "series": row.get("id"), "key": row.get("series_key", {})}
    _check(bool(identity["series"] or identity["key"]), "source series identifier is required")
    relations = tuple(ScopeRelation(
        target=relation["target"], relation=relation["relation"], axis=relation["axis"],
        version=relation["version"], evidence_path=path + f"/scope_relations/{i}",
        includes=tuple(relation.get("includes", ())), excludes=tuple(relation.get("excludes", ())),
    ) for i, relation in enumerate(row.get("scope_relations", ())))
    candidate = Candidate(
        candidate_id=digest(identity), institution_id=document.institution_id, label=label,
        definition=definition, dataset_id=dataset_id, series_id=row.get("id"),
        series_key=row.get("series_key", {}), countries=tuple(row.get("countries", ())),
        dimensions=row.get("dimensions"), frequency=frequency, unit=unit,
        available_start=row.get("available_start"), available_end=row.get("available_end"),
        metadata_revision=document.document_id, source_version=document.source_version,
        evidence=(document.evidence(path, dataset_id, row.get("id")),),
        uncertainties=tuple(sorted(set(warnings))), verification_status="metadata_verified",
        availability_status=row.get("availability_status", "unknown"),
        auth_requirement=row.get("auth_requirement", "unknown"),
        credential_env_var=row.get("credential_env_var"),
    )
    access = None
    if row.get("access") is not None:
        access = SourceAccess.from_dict({"schema_version": 1, **row["access"]})
        pointers["access"] = path + "/access"
    return MetadataRecord(candidate, row.get("concept_id"), labels, VariantAttributes(**variants),
                          row.get("scope"), relations, pointers, access,
                          row.get("structure_document_id"))


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _names(node):
    result = {}
    for child in node:
        if _local(child.tag) == "Name":
            lang = child.get("{http://www.w3.org/XML/1998/namespace}lang", "und")
            _check(lang not in result, "conflicting SDMX language labels")
            result[lang] = child.text or ""
    return result


def _sdmx(document):
    text = document.body.decode("utf-8-sig")
    _check("<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(),
           "DTD and entity declarations are forbidden")
    root = ET.fromstring(text)
    nodes = list(root.iter())
    _check(len(nodes) <= 10000, "SDMX structure node limit exceeded")
    structures = {"dataflows": [], "datastructures": [], "codelists": []}
    seen = set()
    for node in nodes:
        kind = _local(node.tag)
        if kind not in {"Dataflow", "DataStructure", "Codelist"}:
            continue
        identity = (kind, node.get("agencyID"), node.get("id"), node.get("version"))
        _check(identity not in seen and bool(node.get("id")), "duplicate or missing SDMX identity")
        seen.add(identity)
        item = {"agency": node.get("agencyID"), "id": node.get("id"),
                "version": node.get("version"), "names": _names(node)}
        if kind == "Codelist":
            codes = {}
            for child in node:
                if _local(child.tag) == "Code":
                    code = child.get("id")
                    _check(code and code not in codes, "duplicate or missing SDMX code")
                    codes[code] = _names(child)
            item["codes"] = codes
            structures["codelists"].append(item)
        elif kind == "Dataflow":
            refs = [dict(n.attrib) for n in node.iter() if _local(n.tag) == "Ref"]
            _check(len(refs) == 1, "dataflow must reference exactly one DSD")
            item["structure_ref"] = refs[0]
            structures["dataflows"].append(item)
        else:
            dims = []
            for dimension in node.iter():
                if _local(dimension.tag) in {"Dimension", "TimeDimension", "MeasureDimension"}:
                    refs = [dict(n.attrib) for n in dimension.iter() if _local(n.tag) == "Ref"]
                    dims.append({"id": dimension.get("id"), "position": dimension.get("position"),
                                 "references": refs})
            _check(len({d["id"] for d in dims}) == len(dims), "duplicate DSD dimension")
            item["dimensions"] = dims
            structures["datastructures"].append(item)
    warnings = []
    known = {(i["agency"], i["id"], i["version"]) for i in structures["datastructures"]}
    for flow in structures["dataflows"]:
        ref = flow["structure_ref"]
        if (ref.get("agencyID"), ref.get("id"), ref.get("version")) not in known:
            warnings.append("unresolved_dsd:" + flow["id"])
    known_codes = {(i["agency"], i["id"], i["version"]) for i in structures["codelists"]}
    for dsd in structures["datastructures"]:
        for dimension in dsd["dimensions"]:
            for ref in dimension["references"]:
                if ref.get("class") == "Codelist" and (
                    ref.get("agencyID"), ref.get("id"), ref.get("version")
                ) not in known_codes:
                    warnings.append("unresolved_codelist:" + str(dimension["id"]))
    return MetadataResult(document.document_id, structures_json=json.dumps(structures),
                          warnings=tuple(warnings))


def read_metadata(document: MetadataDocument, institution: InstitutionCandidate, *,
                  language: str = "en") -> MetadataResult:
    """No HTTP or Cartesian series generation; supplied identifiers remain source identifiers."""
    _check(document.institution_id == institution.institution_id, "institution mismatch")
    canonical = institution.require_official_document_url(document.source_url)
    _check(canonical == document.source_url, "metadata source URL must be canonical")
    if document.kind == "sdmx_structure":
        return _sdmx(document)
    data = _load(document)
    _check(isinstance(data, dict), "expected metadata JSON object")
    records = []
    if document.kind == "api_catalogue":
        for i, dataset in enumerate(data.get("datasets", ())):
            _check(isinstance(dataset.get("id"), str) and bool(dataset["id"]), "dataset ID missing")
            for j, row in enumerate(dataset.get("series", ())):
                records.append(_normalize(document, dataset["id"], row,
                                          f"/datasets/{i}/series/{j}",
                                          data.get("mappings", {}), language))
                _check(len(records) <= MAX_RECORDS, "metadata record limit exceeded")
    else:
        _check(isinstance(data.get("dataset_id"), str) and bool(data["dataset_id"]),
               "codebook dataset ID missing")
        _check(bool(data.get("sheet")) and isinstance(data.get("columns"), dict),
               "extracted codebook needs a sheet and explicit column mapping")
        for i, cells in enumerate(data.get("rows", ())):
            row = {}
            for field, column in data["columns"].items():
                if column in cells:
                    row[field] = cells[column]
            record = _normalize(document, data["dataset_id"], row,
                                f"/rows/{i}", data.get("mappings", {}), language)
            pointers = {key: (path if key.startswith("mapping.") else
                             f"/rows/{i}/" + data["columns"].get(key, key))
                        for key, path in record.source_fields.items()}
            pointers["sheet"] = "/sheet"
            relations = tuple(replace(
                relation, evidence_path=f"/rows/{i}/" +
                data["columns"].get("scope_relations", "scope_relations") + f"/{j}",
            ) for j, relation in enumerate(record.scope_relations))
            records.append(MetadataRecord(record.candidate, record.concept_id, record.labels,
                                          record.attributes, record.scope, relations,
                                          pointers, record.access, record.structure_document_id))
            _check(len(records) <= MAX_RECORDS, "metadata record limit exceeded")
    _check(len(records) <= MAX_RECORDS, "metadata record limit exceeded")
    for record in records:
        if record.access is not None:
            _check(institution.require_official_document_url(record.access.url) == record.access.url,
                   "data path must be canonical and on a documented official domain")
    return MetadataResult(document.document_id, tuple(records))
