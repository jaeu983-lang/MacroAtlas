"""Confirmed requests to one fixed WDI path; link delivery never opens the URL."""
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import INDICATOR, SOURCE, GDPQuery
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus, TaskStatus, utc
from macro_data_platform.ingestion.worldbank import GDPTransport, WorldBankGDPEngine
from macro_data_platform.ingestion.worldbank_quality import (
    WorldBankAuditedCollection,
    WorldBankValidation,
    reusable,
    verify_completed,
)
from macro_data_platform.orchestration import Orchestrator, StageInput, StageSpec, TaskPlan
from macro_data_platform.orchestration.models import json_snapshot
from macro_data_platform.orchestration.workflow import validate_workflow_task
from macro_data_platform.storage.audit import AuditStore
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.workflow_contracts import ConfirmedSelection
from macro_data_platform.workflow_extensions import ConfirmedDelivery, VariantAttributes


def _query(request, candidate) -> GDPQuery:
    if (candidate.institution_id not in {"worldbank", "INT-04"} or candidate.dataset_id != SOURCE
            or candidate.series_id is not None
            or dict(candidate.series_key) != {
                "source": SOURCE, "country": "USA", "indicator": INDICATOR,
            } or tuple(candidate.countries) != ("USA",) or tuple(request.countries) != ("USA",)
            or dict(request.dimensions) or dict(candidate.dimensions)):
        raise ValueError("Only worldbank / source 2 / USA / NY.GDP.MKTP.CD without filters is supported")
    if (request.frequency != "source" or request.unit_policy != "preserve"
            or request.target_unit is not None or request.vintage_requirement != "latest_available"):
        raise ValueError("Only source frequency, preserved units and latest_available are supported")
    years = (request.period_start, request.period_end)
    if not all(isinstance(year, str) and len(year) == 4 and year.isascii()
               and year.isdecimal() for year in years):
        raise ValueError("The fixed path requires four-digit annual periods")
    return GDPQuery(*(int(year) for year in years))


def build_worldbank_plan(selection: ConfirmedSelection, settings: Settings) -> TaskPlan:
    """Explicit legacy entry; no new wrapper semantics are assigned to v1 JSON."""
    if not isinstance(selection, ConfirmedSelection):
        raise ValueError("Expected a confirmed legacy selection")  # noqa: TRY004 - value contract
    selection = ConfirmedSelection.from_dict(selection.to_dict())
    candidate = next(c for c in selection.proposal.candidates
                     if c.candidate_id == selection.candidate_id)
    query = _query(selection.request, candidate)
    if candidate.auth_requirement != "none" or candidate.credential_env_var is not None:
        raise ValueError("The fixed public World Bank path uses no API credentials")
    if selection.output.format != "raw_json":
        raise ValueError("Only raw_json is implemented; CSV/XLSX export is unsupported")
    if (selection.output.relative_dir != f"{settings.data_dir}/raw".replace("\\", "/")
            or selection.output.resolve_under(settings.project_root) != settings.raw_dir):
        raise ValueError("Only the configured raw directory is supported; no output relocation")
    return TaskPlan((StageSpec("collect", "worldbank_gdp", {
        "start_year": query.start_year, "end_year": query.end_year,
    }),))


def _plan(confirmed: ConfirmedDelivery, settings: Settings, at: datetime) -> TaskPlan | None:
    confirmed = ConfirmedDelivery.from_dict(confirmed.to_dict())
    ConfirmedDelivery(confirmed.offer, confirmed.delivery, at, "followup")
    query = _query(confirmed.offer.request, confirmed.offer.candidate)
    if confirmed.offer.requirements not in (
        VariantAttributes(), VariantAttributes(price_basis="nominal"),
    ):
        raise ValueError("Variant filtering is unsupported by the fixed World Bank path")
    selected = {item.link_id: item for item in confirmed.offer.links}
    # Only the already documented fixed query URL is delivered. This does not verify it online.
    if any(selected[key].url != query.url for key in confirmed.delivery.link_ids):
        raise ValueError("Selected data links must match the fixed World Bank query URL")
    if confirmed.delivery.mode == "link":
        return None
    offer = confirmed.offer
    plan = build_worldbank_plan(ConfirmedSelection(
        offer.request, offer.proposal.proposal, offer.candidate_id, offer.proposal.proposal.revision,
        confirmed.delivery.file, confirmed.confirmed_at, confirmed.confirmation_method,
    ), settings)
    if confirmed.delivery.mode == "both":
        return TaskPlan((*plan.stages, StageSpec("deliver", "worldbank_delivery")))
    return plan


def _links(confirmed: ConfirmedDelivery) -> list[dict]:
    selected = {item.link_id: item for item in confirmed.offer.links}
    return [selected[key].to_dict() for key in confirmed.delivery.link_ids]


class _LinkStage:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def run(self, request: StageInput) -> StageResult:
        try:
            _, confirmed, _ = self.dispatcher._preflight(request.task_id)
        except ValueError:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SEMANTIC_AMBIGUITY,
                               warnings=("Delivery conditions changed; confirmation review required.",))
        return StageResult(StageStatus.SUCCEEDED, {
            "mode": "both", "collection": request.upstream, "links": _links(confirmed),
            "link_verification": "supplied_evidence_only; no link HTTP request",
        }, request.input_refs)


class WorldBankRequestDispatcher:
    """Product execution entry. Existing unbound Orchestrator APIs remain available."""

    def __init__(self, settings: Settings, store: HistoryStore, *,
                 transport: GDPTransport | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 gate_a: bool = False):
        if settings.database_path != store.settings.database_path:
            raise ValueError("Dispatcher and history must use the same configured storage")
        self.settings, self.store, self.transport, self.clock = settings, store, transport, clock
        if type(gate_a) is not bool:
            raise ValueError("gate_a must be an explicit boolean")
        self.gate_a = gate_a
        self.audit = AuditStore(store, clock=clock) if gate_a else None

    def _now(self):
        at = self.clock()
        utc(at)
        return at

    def _preflight(self, task_id):
        with self.store.transaction() as connection:
            doc = self.store.load(connection, task_id)
            if "workflow_context" not in doc:
                raise ValueError("Dispatcher requires a linked confirmed delivery task")
            validate_workflow_task(self.store, connection, doc, self._now(), allow_link=True)
            confirmed = ConfirmedDelivery.from_dict(doc["workflow_context"]["confirmation"])
            plan = _plan(confirmed, self.settings, self._now())
            if self.gate_a and plan is not None:
                collect = plan.stages[0]
                plan = TaskPlan((
                    StageSpec("collect", "worldbank_collect_audit", collect.input_data),
                    StageSpec("validate", "worldbank_validate", collect.input_data),
                    *plan.stages[1:],
                ))
            if doc["plan"] is not None and (plan is None or doc["plan"] != plan.snapshot()):
                raise ValueError("Saved plan differs from the confirmed World Bank request")
        if self.gate_a and plan is not None and doc["status"] == TaskStatus.COMPLETED:
            verify_completed(self.audit, doc)
        return doc, confirmed, plan

    def _runner(self):
        engines = {
            ("worldbank_gdp", "1"): WorldBankGDPEngine(self.settings, self.transport),
            ("worldbank_delivery", "1"): _LinkStage(self),
        }
        if self.gate_a:
            engines.update({
                ("worldbank_collect_audit", "1"): WorldBankAuditedCollection(
                    self.audit, self.transport, settings=self.settings),
                ("worldbank_validate", "1"): WorldBankValidation(self.audit),
            })
        return Orchestrator(self.store, engines, clock=self.clock,
                            reuse_validator=(lambda spec, stage: reusable(self.audit, spec, stage))
                            if self.gate_a else None)

    def prepare(self, task_id: str) -> dict:
        doc, _, plan = self._preflight(task_id)
        if plan is not None:
            self._runner().plan(task_id, plan)
            return self.store.get(task_id)
        return doc

    def run(self, task_id: str) -> dict:
        doc, confirmed, plan = self._preflight(task_id)
        if plan is not None:
            self._runner().plan(task_id, plan)
            return self._runner().run(task_id)
        # A dedicated transaction, not a collector stage/engine, handles link-only work.
        with self.store.transaction() as connection:
            doc = self.store.load(connection, task_id)
            validate_workflow_task(self.store, connection, doc, self._now(), allow_link=True)
            if doc["status"] == TaskStatus.COMPLETED:
                return doc
            if doc["status"] != TaskStatus.CREATED or doc["cancel_requested"]:
                raise ValueError("Link delivery requires an uncancelled created task")
            at = self._now().isoformat()
            doc["delivery_result"] = {
                "mode": "link", "links": _links(confirmed),
                "link_verification": "supplied_evidence_only; no HTTP request or local data files",
            }
            doc["status"] = TaskStatus.COMPLETED
            doc["attempts"].append({"attempt_no": 1, "token": str(uuid4()),
                                    "started_at": at, "finished_at": at,
                                    "status": TaskStatus.COMPLETED})
            self.store.save(connection, doc)
            self.store.event(connection, task_id, {
                "kind": "LINK_DELIVERED", "at": at, "task_status": TaskStatus.COMPLETED,
                "confirmation_fingerprint": confirmed.fingerprint,
            })
            return json_snapshot(doc)

    def resume(self, task_id: str, *, approved: bool = False) -> dict:
        _, _, plan = self._preflight(task_id)
        if plan is None:
            raise ValueError("Link delivery has no collector attempt to resume")
        return self._runner().resume(task_id, approved=approved)
