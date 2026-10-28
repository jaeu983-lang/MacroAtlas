"""Fixed, documented metadata selections and strict SDMX-ML 2.1 contracts.

Selections are not a general catalogue or observation ingestion API. See the
Iteration 32 route audit for official ID, access and format evidence.
"""
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from macro_data_platform.connectors.sdmx import (
    MAX_SDMX_RESPONSE_BYTES,
    BISClient,
    BundesbankClient,
    ECBClient,
    EurostatClient,
    IMFClient,
    INSEEClient,
    OECDClient,
    SdmxApiResponse,
)
from macro_data_platform.discovery.source_registry import get_source_profile
from macro_data_platform.metadata.adapters import parse_sdmx_structure

MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"


@dataclass(frozen=True)
class MetadataSelection:
    institution_id: str
    client: type
    method: str
    arguments: tuple[str, ...]
    path: str
    kind: str
    agency: str
    resource_id: str
    version: str | None
    ready: bool = True
    iteration: int = 32

    @property
    def url(self):
        return self.client.root + self.path

    @property
    def operation(self):
        return ("structure" if self.method in {"get_structure", "get_codelist"}
                else self.kind.lower())


SDMX_SELECTIONS = {
    "bis": MetadataSelection("INT-02", BISClient, "get_structure",
        ("dataflow", "BIS", "WS_TC", "2.0"),
        "/structure/dataflow/BIS/WS_TC/2.0", "Dataflow", "BIS", "WS_TC", "2.0"),
    "oecd": MetadataSelection("INT-03", OECDClient, "get_structure",
        ("dataflow", "OECD.SDD.NAD", "DSD_NAMAIN1@DF_QNA", "1.1"),
        "/dataflow/OECD.SDD.NAD/DSD_NAMAIN1@DF_QNA/1.1",
        "Dataflow", "OECD.SDD.NAD", "DSD_NAMAIN1@DF_QNA", "1.1"),
    "ecb": MetadataSelection("EU-01", ECBClient, "get_datastructure",
        ("ECB", "ECB_EXR1", "1.0"), "/datastructure/ECB/ECB_EXR1/1.0",
        "DataStructure", "ECB", "ECB_EXR1", "1.0"),
    "eurostat": MetadataSelection("EU-02", EurostatClient, "get_dataflow",
        ("NAMA_10_GDP", "ESTAT", "1.0"), "/dataflow/ESTAT/NAMA_10_GDP/1.0",
        "Dataflow", "ESTAT", "NAMA_10_GDP", "1.0"),
    "bundesbank": MetadataSelection("EU-03", BundesbankClient, "get_dataflow",
        ("BBEX3",), "/metadata/dataflow/BBK/BBEX3",
        "Dataflow", "BBK", "BBEX3", None),
    "insee": MetadataSelection("EU-05", INSEEClient, "get_datastructure",
        ("IPC-2015-COICOP", "1.0"), "/datastructure/FR1/IPC-2015-COICOP/1.0",
        "DataStructure", "FR1", "IPC-2015-COICOP", "1.0"),
    "insee-nature": MetadataSelection("EU-05", INSEEClient, "get_codelist",
        ("CL_NATURE", "1.0"), "/codelist/FR1/CL_NATURE/1.0",
        "Codelist", "FR1", "CL_NATURE", "1.0", iteration=33),
    "imf-cpi": MetadataSelection("INT-01", IMFClient, "get_dataflow",
        ("IMF.STA", "CPI", "latest"), "/dataflow/IMF.STA/CPI/latest",
        "Dataflow", "IMF.STA", "CPI", None, iteration=34),
}


def fetch_sdmx_metadata(source, settings, transport=None):
    selection = SDMX_SELECTIONS[source]
    client = selection.client(settings, transport)
    return getattr(client, selection.method)(*selection.arguments)


def validate_sdmx_metadata(source: str, response: SdmxApiResponse) -> dict:
    """Validate source, exact request, namespace, identity and structural contents.

    XML only is negotiated in this iteration. JSON/error envelopes and any
    unreviewed media type fail closed rather than guessing a provider schema.
    Unresolved linked structures remain explicit; they are not downloaded.
    """
    selection = SDMX_SELECTIONS[source]
    result = {"status": "needs_review", "scope": "metadata_only",
              "observations_accepted": False, "complete_dataset_assessed": False}

    def fail(reason):
        return {**result, "reason": reason}

    if (response.institution_id != selection.institution_id
            or response.source_agency != get_source_profile(selection.institution_id).name
            or response.source_url != selection.url
            or response.operation != selection.operation):
        return fail("source_or_request_mismatch")
    if response.http_status != 200:
        return fail("http_status_not_success")
    if not isinstance(response.body, bytes) or not 0 < len(response.body) <= MAX_SDMX_RESPONSE_BYTES:
        return fail("empty_or_oversized_response")
    media = response.content_type.split(";", 1)[0].strip().lower()
    if media not in {"application/xml", "text/xml", "application/vnd.sdmx.structure+xml"}:
        return fail("unexpected_media_type")
    try:
        text = response.body.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            return fail("unsafe_xml_declaration")
        root = ET.fromstring(text)
        nodes = list(root.iter())
        if len(nodes) > 10000:
            return fail("structure_node_limit")
        if any(n.tag.rsplit("}", 1)[-1] in {"Error", "ErrorMessage", "Fault"} for n in nodes):
            return fail("source_error_envelope")
        if root.tag != f"{{{MESSAGE}}}Structure":
            return fail("unexpected_xml_root_or_namespace")
        headers = root.findall(f"{{{MESSAGE}}}Header")
        if len(headers) != 1 or not (headers[0].findtext(f"{{{MESSAGE}}}ID") or "").strip():
            return fail("missing_response_identifier")
        containers = root.findall(f"{{{MESSAGE}}}Structures")
        if len(containers) != 1:
            return fail("missing_structures")
        tag = f"{{{STRUCTURE}}}{selection.kind}"
        group = {"Dataflow": "Dataflows", "DataStructure": "DataStructures",
                 "Codelist": "Codelists"}[selection.kind]
        selected = containers[0].findall(f"{{{STRUCTURE}}}{group}/{tag}")
        if len(selected) != 1:
            return fail("empty_or_ambiguous_selection")
        node = selected[0]
        if (node.get("agencyID") != selection.agency
                or node.get("id") != selection.resource_id
                or not node.get("version")
                or selection.version is not None and node.get("version") != selection.version):
            return fail("selected_identity_mismatch")
        if node.get("isExternalReference", "false").lower() != "false":
            return fail("selected_resource_is_stub")
        if not any((n.text or "").strip() for n in node.findall(f"{{{COMMON}}}Name")):
            return fail("missing_resource_name")
        if selection.kind == "Dataflow":
            refs = node.findall(f"{{{STRUCTURE}}}Structure/Ref")
            if (len(refs) != 1 or refs[0].get("class") != "DataStructure"
                    or refs[0].get("package") != "datastructure"
                    or any(not refs[0].get(k) for k in ("id", "agencyID", "version"))):
                return fail("invalid_dsd_reference")
        elif selection.kind == "Codelist":
            codes = node.findall(f"{{{STRUCTURE}}}Code")
            if (not codes or any(not n.get("id") for n in codes)
                    or len({n.get("id") for n in codes}) != len(codes)
                    or any(not any((label.text or "").strip() for label in
                                   n.findall(f"{{{COMMON}}}Name")) for n in codes)):
                return fail("empty_or_invalid_codelist")
        else:
            dimensions = node.findall(
                f"{{{STRUCTURE}}}DataStructureComponents/{{{STRUCTURE}}}DimensionList/*")
            if (not dimensions or any(not n.get("id") for n in dimensions)
                    or len({n.get("id") for n in dimensions}) != len(dimensions)
                    or any(n.tag not in {f"{{{STRUCTURE}}}{kind}" for kind in
                           ("Dimension", "TimeDimension", "MeasureDimension")}
                           for n in dimensions)):
                return fail("invalid_or_empty_dimensions")
        structures, warnings = parse_sdmx_structure(response.body)
    except (ValueError, UnicodeError, ET.ParseError, RecursionError):
        return fail("invalid_structure")
    return {**result, "status": "metadata_contract_validated",
            "reason": "selected_metadata_present", "entry_count": 1,
            "selected": {"kind": selection.kind, "agency": selection.agency,
                         "id": selection.resource_id, "version": node.get("version")},
            "structure_counts": {k: len(v) for k, v in structures.items()},
            "warnings": list(warnings)}
