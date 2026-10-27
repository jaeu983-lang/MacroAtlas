"""Small, bounded SDMX-ML 2.1 structure metadata reader."""
from datetime import datetime
from xml.etree import ElementTree

from macro_data_platform.metadata.normalize import (
    NORMALIZED_FIELDS,
    _field,
    _unknown,
    _valid_source,
)
from macro_data_platform.performance.metrics import measured_phase

MAX_XML_BYTES = 2 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _texts(element: ElementTree.Element) -> dict[str, str]:
    result = {}
    for child in element:
        if _local(child.tag) == "Name" and child.text and child.text.strip():
            result[child.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "und")] = child.text.strip()
    return result


def _named_children(element: ElementTree.Element, wanted: str) -> list[ElementTree.Element]:
    return [child for child in element.iter() if _local(child.tag) == wanted]


@measured_phase("parse")
def parse_sdmx_structure_xml(raw: bytes, *, source_agency: str, source_url: str,
                             retrieved_at: datetime, raw_path: str) -> list[dict]:
    """Parse Dataflow, DSD, and Codelist names/references without semantic inference."""
    _valid_source(source_url)
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_XML_BYTES:
        raise ValueError("SDMX XML must be nonempty and at most two MiB")
    upper = raw.upper()
    if b"\x00" in raw or b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("SDMX XML DTD and entity declarations are prohibited")
    if (retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None
            or retrieved_at.utcoffset().total_seconds()):
        raise ValueError("retrieved_at must be UTC")
    if not isinstance(source_agency, str) or not source_agency.strip():
        raise ValueError("source_agency is required")
    try:
        root = ElementTree.fromstring(raw)
    except (ElementTree.ParseError, ValueError):
        raise ValueError("SDMX source is not valid XML") from None
    records = []
    for element in root.iter():
        kind = _local(element.tag)
        if kind not in {"Dataflow", "DataStructure", "Codelist"}:
            continue
        identifier = element.attrib.get("id")
        if not identifier:
            continue
        ref = f"/{kind}[@id='{identifier}']"
        names = _texts(element)
        fields = {name: _unknown("SDMX structure message does not define this field")
                  for name in NORMALIZED_FIELDS}
        fields["name"] = ({"value": names, "state": "known", "source_refs": [ref + "/Name"],
                           "reason": None} if names else _unknown("SDMX Name is absent"))
        attributes = {"sdmx_type": kind, "agency_id": element.attrib.get("agencyID"),
                      "version": element.attrib.get("version")}
        if kind == "Dataflow":
            refs = [node.attrib.get("id") for node in element.iter()
                    if _local(node.tag) in {"Ref", "Structure"} and node.attrib.get("id")]
            attributes["structure_references"] = refs
        elif kind == "DataStructure":
            dimensions = []
            for child in element.iter():
                if _local(child.tag) in {"Dimension", "TimeDimension", "MeasureDimension"}:
                    dims = _texts(child)
                    dim_id = child.attrib.get("id")
                    if dim_id:
                        dimensions.append({"id": dim_id, "name": dims,
                                           "position": child.attrib.get("position")})
            if dimensions:
                fields["dimensions"] = _field(dimensions, ref + "/DataStructureComponents")
        elif kind == "Codelist":
            codes = []
            for child in element.iter():
                if _local(child.tag) == "Code" and child.attrib.get("id"):
                    codes.append({"id": child.attrib["id"], "name": _texts(child)})
            attributes["codes"] = codes
        records.append({
            "schema_version": "normalized-metadata-v1", "entity_type": kind.lower(),
            "source_agency": source_agency, "source_url": source_url,
            "retrieved_at": retrieved_at.isoformat(),
            "source_version": element.attrib.get("version"),
            "dataset_id": _unknown("not exposed for this SDMX structure component"),
            "identifier": _field(identifier, ref + "/@id"), "fields": fields,
            "source_attributes": attributes, "request_context": {"format": "SDMX-ML 2.1"},
            "raw_ref": {"path": raw_path, "xml_pointer": ref},
            "metadata_completeness": "partial",
        })
    if not records:
        raise ValueError("SDMX message contains no supported structures")
    return records
