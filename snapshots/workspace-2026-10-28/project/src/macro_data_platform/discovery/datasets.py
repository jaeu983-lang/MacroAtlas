"""Versioned declarations for explicitly supported API and official-file datasets."""
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DatasetProfile:
    profile_id: str
    institution_id: str
    dataset_id: str
    title: str
    access_method: str
    adapter_id: str
    validator_id: str
    source_url: str
    documentation_urls: tuple[str, ...]
    fixed_parameters: tuple[tuple[str, str], ...] = ()
    unit: str | None = None
    frequency: str | None = None
    missing_tokens: tuple[str, ...] = ("",)
    notes: tuple[str, ...] = ()
    version: int = 1

    def __post_init__(self):
        for field in ("documentation_urls", "missing_tokens", "notes"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        object.__setattr__(self, "fixed_parameters", tuple(tuple(pair) for pair in self.fixed_parameters))
        if (not re.fullmatch(r"[a-z][a-z0-9_.-]{1,99}", self.profile_id)
                or not re.fullmatch(r"(?:INT|US|EU|JP)-[0-9]{2}", self.institution_id)
                or self.access_method not in {"api", "official_file"}
                or type(self.version) is not int or self.version < 1):
            raise ValueError("Invalid dataset identity, access method or version")
        if not self.documentation_urls or not self.dataset_id or not self.title:
            raise ValueError("Dataset requires source identifiers, title and official documentation")
        for value in (self.source_url, *self.documentation_urls):
            parts = urlsplit(value)
            if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                    or parts.fragment or parts.port is not None):
                raise ValueError("Dataset references require public HTTPS URLs")
        if urlsplit(self.source_url).query:
            raise ValueError("Dataset source URL must keep parameters separate")
        names = [name for name, _ in self.fixed_parameters]
        if len(names) != len(set(names)) or any(name.casefold() in {
            "key", "api_key", "registrationkey", "userid", "appid",
        } for name in names):
            raise ValueError("Dataset declarations cannot contain credentials or duplicate fields")
        if any(not isinstance(value, str) or len(value) > 2048 for pair in self.fixed_parameters for value in pair):
            raise ValueError("Dataset fixed selections require bounded text")

    def to_dict(self) -> dict:
        document = asdict(self)
        document["evidence_scope"] = "documented_route_and_synthetic_contract; not live ingestion"
        return document

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def fixed(self) -> dict[str, str]:
        return dict(self.fixed_parameters)


_TIC_PAGE = ("https://home.treasury.gov/data/treasury-international-capital-tic-system-home-page/"
             "tic-forms-instructions/securities-b-portfolio-holdings-of-us-and-foreign-securities")
_TIC_ROOT = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/"
_BLS_DOC = "https://www.bls.gov/developers/api_signature.htm"
_BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
_PROFILES = (
    DatasetProfile(
        "fred.gdp", "US-02", "GDP", "FRED GDP observation page", "api", "fred_observations", "fred_page",
        "https://api.stlouisfed.org/fred/series/observations",
        ("https://fred.stlouisfed.org/docs/api/fred/series_observations.html",),
        (("series_id", "GDP"),), missing_tokens=(".",),
        notes=("An explicit page, not full history; unit/frequency and original agency require metadata.",),
    ),
    DatasetProfile(
        "census.acs2023.population", "US-06", "2023/acs/acs5", "ACS 2023 five-year population table",
        "api", "census_table", "census_table", "https://api.census.gov/data/2023/acs/acs5",
        ("https://www.census.gov/data/developers/guidance/api-user-guide.Example_API_Queries.html",),
        (("variables", "NAME,B01001_001E"),),
        notes=("Reference-year dataset path is not an immutable release vintage; no sentinel conversion.",),
    ),
    DatasetProfile(
        "bls.unemployment", "US-05", "LNS14000000", "BLS selected unemployment series, v1",
        "api", "bls_v1", "bls_v1", _BLS_URL, (_BLS_DOC,), (("series_ids", "LNS14000000"),),
        notes=("No key/v2; values and footnotes retained; no inferred unit or frequency.",),
    ),
    DatasetProfile(
        "bls.cpi", "US-05", "CUUR0000SA0", "BLS selected CPI series, v1",
        "api", "bls_v1", "bls_v1", _BLS_URL, (_BLS_DOC,), (("series_ids", "CUUR0000SA0"),),
        notes=("No key/v2; M13 remains the source Annual period, not a thirteenth month.",),
    ),
    DatasetProfile(
        "tic.mfh.history", "US-03", "mfhhis01", "Major foreign holders of Treasury securities, history",
        "official_file", "tic_csv", "tic_mfh_blocks", _TIC_ROOT + "mfhhis01.csv", (_TIC_PAGE,),
        (("file_id", "mfhhis01"),), unit="in billions of dollars", frequency="monthly",
        missing_tokens=("", "n.a.", ".."),
        notes=("Multiple year/month header blocks, aggregates and notes retained; full file, no country filter.",
               "Treasury securities holdings are not total country debt or all-sector liabilities."),
    ),
    DatasetProfile(
        "tic.treasury_holdings.2023_01", "US-03", "slt3d", "Table 3D Treasury holdings, January 2023 snapshot",
        "official_file", "tic_csv", "tic_table3d", _TIC_ROOT + "slt3d.csv", (_TIC_PAGE,),
        (("file_id", "slt3d"), ("source_period", "2023-01")), unit="Millions of dollars", frequency="monthly",
        missing_tokens=("", "n.a."),
        notes=("The official linked file inspected for structure is January 2023, not a latest-data guarantee.",
               "Region/total/memo rows and missing text are preserved, without country-code mapping."),
    ),
    DatasetProfile(
        "boe.bank_rate", "EU-04", "IUDBEDR", "Official Bank Rate CSV download",
        "official_file", "boe_csv", "boe_tn", "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp",
        ("https://www.bankofengland.co.uk/boeapps/database/help.asp",),
        (("series_id", "IUDBEDR"), ("CSVF", "TN")), missing_tokens=("", ".."),
        notes=("Native reporting dates only; no calendar filling, month-end alignment or inferred unit.",),
    ),
)


def all_dataset_profiles() -> tuple[DatasetProfile, ...]:
    return _PROFILES


def get_dataset_profile(profile_id: str) -> DatasetProfile:
    for profile in _PROFILES:
        if profile.profile_id == profile_id:
            return profile
    raise ValueError("Dataset profile is not registered; a source-specific contract is required")
