"""Source-specific bindings from registered dataset selections to existing clients."""
from collections.abc import Mapping

from macro_data_platform.connectors.bls import BLSClient
from macro_data_platform.connectors.census import CensusClient
from macro_data_platform.connectors.fred import FREDClient
from macro_data_platform.connectors.official_files import BankOfEnglandFileClient, TICFileClient
from macro_data_platform.discovery.datasets import DatasetProfile


def _fields(parameters: Mapping, allowed: set[str], required: set[str]) -> dict:
    if not isinstance(parameters, Mapping) or not required <= set(parameters) or set(parameters) - allowed:
        raise ValueError("Dataset request has missing or unregistered fields; source selection is fixed")
    return dict(parameters)


class FREDObservationBinding:
    def __init__(self, client: FREDClient):
        self.client = client

    def fetch(self, profile: DatasetProfile, parameters: Mapping):
        query = _fields(parameters, {"start", "end", "limit", "offset", "realtime_start", "realtime_end"}, {"start", "end"})
        return self.client.get_observations_page(profile.fixed["series_id"], **query)


class CensusTableBinding:
    def __init__(self, client: CensusClient):
        self.client = client

    def fetch(self, profile: DatasetProfile, parameters: Mapping):
        query = _fields(parameters, {"predicates"}, {"predicates"})
        return self.client.get_data(profile.dataset_id, profile.fixed["variables"].split(","), query["predicates"])


class BLSV1Binding:
    def __init__(self, client: BLSClient):
        self.client = client

    def fetch(self, profile: DatasetProfile, parameters: Mapping):
        query = _fields(parameters, {"start_year", "end_year"}, {"start_year", "end_year"})
        return self.client.get_data(profile.fixed["series_ids"].split(","), **query)


class TICCSVBinding:
    def __init__(self, client: TICFileClient):
        self.client = client

    def fetch(self, profile: DatasetProfile, parameters: Mapping):
        _fields(parameters, set(), set())
        return self.client.get_file(profile.fixed["file_id"])


class BoECSVBinding:
    def __init__(self, client: BankOfEnglandFileClient):
        self.client = client

    def fetch(self, profile: DatasetProfile, parameters: Mapping):
        query = _fields(parameters, {"start", "end"}, {"start", "end"})
        return self.client.get_bank_rate(**query)


def default_dataset_bindings(settings) -> dict:
    return {
        "fred_observations": FREDObservationBinding(FREDClient(settings)),
        "census_table": CensusTableBinding(CensusClient(settings)),
        "bls_v1": BLSV1Binding(BLSClient(settings)),
        "tic_csv": TICCSVBinding(TICFileClient(settings)),
        "boe_csv": BoECSVBinding(BankOfEnglandFileClient(settings)),
    }
