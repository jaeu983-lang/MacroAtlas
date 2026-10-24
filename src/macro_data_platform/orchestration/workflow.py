"""Structured confirmation service. No discovery, HTTP, exporters or source plan builders."""
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from macro_data_platform.contracts import TaskStatus, required, utc
from macro_data_platform.orchestration.models import json_snapshot
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.workflow_contracts import DataRequest
from macro_data_platform.workflow_extensions import (
    ConfirmedDelivery,
    DataLink,
    DeliveryOffer,
    DeliverySpec,
    GroupedProposal,
    VariantAttributes,
)


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def _draft(request, proposal, candidate_id=None, delivery=None, links=(), requirements=None):
    if not isinstance(request, DataRequest) or not isinstance(proposal, GroupedProposal):
        raise ValueError("expected request and grouped proposal")  # noqa: TRY004 - value contract
    if request.request_id != proposal.proposal.request_id:
        raise ValueError("request identity mismatch")
    if candidate_id is not None and candidate_id not in {
        item.candidate_id for item in proposal.proposal.candidates
    }:
        raise ValueError("unknown selected candidate")
    delivery = DeliverySpec() if delivery is None else delivery
    requirements = VariantAttributes() if requirements is None else requirements
    if not isinstance(delivery, DeliverySpec) or not isinstance(requirements, VariantAttributes):
        raise ValueError("expected delivery and variant settings")  # noqa: TRY004 - value contract
    links = tuple(links)
    if not all(isinstance(item, DataLink) for item in links):
        raise ValueError("expected data links")
    if len({item.link_id for item in links}) != len(links):
        raise ValueError("duplicate data links")
    value = {"request": request.to_dict(), "proposal": proposal.to_dict(), "candidate_id": candidate_id,
                 "delivery": delivery.to_dict(), "requirements": requirements.to_dict(),
                 "links": [item.to_dict() for item in links]}
    # Bound per-request reads; revision history lives in append-only events, not this snapshot.
    if (len(proposal.proposal.candidates) > 50 or len(links) > 100
            or len(json.dumps(value, ensure_ascii=False).encode()) > 262144):
        raise ValueError("workflow snapshot budget exceeded")
    return value


def _restore(draft):
    return {"request": DataRequest.from_dict(draft["request"]),
                "proposal": GroupedProposal.from_dict(draft["proposal"]),
                "candidate_id": draft["candidate_id"],
                "delivery": DeliverySpec.from_dict(draft["delivery"]),
                "links": tuple(DataLink.from_dict(item) for item in draft["links"]),
                "requirements": VariantAttributes.from_dict(draft["requirements"])}


def _assess(draft: dict, at: datetime, method: str | None) -> dict:
    if method not in (None, "explicit_request", "followup"):
        raise ValueError("explicit confirmation method required")
    values = _restore(draft)
    request, delivery = values["request"], values["delivery"]
    questions = []

    def ask(field, kind="input", choices=()):
        questions.append({"field": field, "kind": kind, "choices": list(choices)})

    if values["candidate_id"] is None:
        ask("candidate_id", choices=[c.candidate_id for c in values["proposal"].proposal.candidates])
    for field in ("concept", "countries", "dimensions", "period_start", "period_end",
                  "frequency", "unit_policy", "vintage_requirement"):
        value = getattr(request, field)
        if value is None or (field == "countries" and not value):
            ask(field)
    if request.unit_policy == "convert" and request.target_unit is None:
        ask("target_unit")
    offer = None
    modes = ()
    formats = ()
    warnings = []
    if values["candidate_id"] is not None:
        args = {key: value for key, value in values.items() if key != "delivery"}
        try:
            offer = DeliveryOffer(**args)
        except ValueError:
            ask("links_context", "review")
            # Offer file choices without pretending stale links have become valid.
            offer = DeliveryOffer(**{**args, "links": ()})
        modes, formats = offer.available_modes(at), offer.file_formats
        warnings = list(offer.candidate.uncertainties)
        candidate = offer.candidate
        for field in ("definition", "dimensions", "available_start", "available_end"):
            if getattr(candidate, field) is None:
                ask("candidate." + field, "review")
        if not (candidate.series_id or candidate.series_key):
            ask("candidate.identifier", "review")
        if not candidate.evidence:
            ask("candidate.evidence", "review")
        for field in ("verification_status", "availability_status"):
            if getattr(candidate, field) == "unknown":
                ask("candidate." + field, "review")
    if delivery.mode is None:
        ask("delivery.mode", choices=modes)
    elif offer is not None and delivery.mode not in modes:
        ask("delivery.mode", "review", modes)
    if delivery.mode in ("file", "both"):
        if delivery.file is None:
            ask("delivery.file", choices=formats)
        elif offer is not None and delivery.file.format not in formats:
            ask("delivery.file", "review", formats)
    if delivery.mode in ("link", "both"):
        usable = {item.link_id for item in offer.links if item.usable_at(at)} if offer else set()
        if not delivery.link_ids:
            ask("delivery.link_ids", choices=sorted(usable))
        elif not set(delivery.link_ids).issubset(usable):
            ask("delivery.link_ids", "review", sorted(usable))
    confirmed = None
    if not questions:
        try:
            check = ConfirmedDelivery(offer, delivery, at, method or "followup")
            if method is not None:
                confirmed = check.to_dict()
        except ValueError:
            ask("selection_consistency", "review")
    state = ("NEEDS_REVIEW" if any(q["kind"] == "review" for q in questions)
             else "NEEDS_INPUT" if questions else "CONFIRMED" if confirmed else "READY")
    return {"state": state, "questions": questions, "available_modes": list(modes),
            "warnings": warnings, "confirmation": confirmed,
            "link_statuses": [{"link_id": item.link_id, "status": item.status,
                               "usable": (offer is not None and item in offer.links
                                          and item.usable_at(at)),
                               "manual_filter_required": item.manual_filter_required,
                               "reason": item.reason, "restrictions": list(item.restrictions)}
                              for item in values["links"]]}


class WorkflowService:
    """Callers supply evidence and structured user answers; no automatic consent."""

    def __init__(self, store: HistoryStore, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.store, self.clock = store, clock

    def _now(self):
        at = self.clock()
        utc(at)
        return at

    def _save(self, connection, doc, kind):
        self.store.save(connection, doc)
        self.store.event(connection, doc["task_id"], {
            "kind": kind, "at": self._now().isoformat(),
            "snapshot": doc["workflow_request"],
        })

    def begin(self, request: DataRequest, proposal: GroupedProposal, *, source_task_id=None,
              idempotency_key=None, confirmation_method=None, **settings) -> dict:
        draft = _draft(request, proposal, **settings)
        identity = _digest({"draft": draft, "source_task_id": source_task_id,
                                "confirmation_method": confirmation_method})
        if idempotency_key is not None:
            required(idempotency_key, "idempotency_key")
        at = self._now()
        assessment = _assess(draft, at, confirmation_method)
        with self.store.transaction() as connection:
            prior = self.store.by_key(connection, idempotency_key)
            if prior is not None:
                if prior.get("workflow_request", {}).get("initial_identity") != identity:
                    raise ValueError("idempotency key conflicts with another workflow")
                return json_snapshot(prior)
            if source_task_id is not None:
                source = self.store.load(connection, source_task_id)
                if source["status"] != TaskStatus.COMPLETED:
                    raise ValueError("source task must be completed")
            doc = self.store.document(request.text, at.isoformat())
            doc["workflow_request"] = dict(schema_version=1, revision=1,
                source_task_id=source_task_id, initial_identity=identity, draft=draft,
                work_task_id=None, **assessment)
            self.store.insert(connection, doc, idempotency_key)
            self._save(connection, doc, "WORKFLOW_CREATED")
            return json_snapshot(doc)

    def get(self, workflow_id: str) -> dict:
        doc = self.store.get(workflow_id)
        self._workflow(doc)
        return doc

    @staticmethod
    def _workflow(doc):
        if "workflow_request" not in doc:
            raise ValueError("expected workflow request")
        if doc["cancel_requested"] or doc["status"] == TaskStatus.CANCELLED:
            raise ValueError("workflow request cancelled")
        return doc["workflow_request"]

    def revise(self, workflow_id: str, *, expected_revision: int,
               confirmation_method=None, **changes) -> dict:
        at = self._now()
        with self.store.transaction() as connection:
            doc = self.store.load(connection, workflow_id)
            workflow = self._workflow(doc)
            if type(expected_revision) is not int or expected_revision != workflow["revision"]:
                raise ValueError("stale workflow revision")
            values = _restore(workflow["draft"])
            if set(changes) - set(values):
                raise ValueError("unknown workflow update field")
            draft = _draft(**{**values, **changes})
            if draft["request"]["request_id"] != workflow["draft"]["request"]["request_id"]:
                raise ValueError("workflow request identity is immutable")
            assessment = _assess(draft, at, confirmation_method)
            same = draft == workflow["draft"]
            # Revalidation never refreshes original consent time or silently re-confirms changes.
            if same and workflow["confirmation"] and not assessment["questions"]:
                assessment["confirmation"] = workflow["confirmation"]
                assessment["state"] = workflow["state"]
            if same and all(workflow[key] == value for key, value in assessment.items()):
                return json_snapshot(doc)
            if same and workflow["confirmation"] and not assessment["questions"]:
                # An unused link's clock-dependent usability is not a changed user selection.
                workflow.update(**assessment)
                self._save(connection, doc, "WORKFLOW_REVALIDATED")
                return json_snapshot(doc)
            if workflow["revision"] >= 100:
                raise ValueError("workflow revision budget exceeded")
            child_id = workflow["work_task_id"]
            if child_id:
                child = self.store.load(connection, child_id)
                if child["status"] not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                    child["cancel_requested"] = True
                    if child["active_token"] is None:
                        child["status"] = TaskStatus.CANCELLED
                    self.store.save(connection, child)
                    self.store.event(connection, child_id, {
                        "kind": "WORKFLOW_INVALIDATED", "at": at.isoformat(),
                    })
            workflow.update(draft=draft, revision=workflow["revision"] + 1,
                            work_task_id=None, **assessment)
            self._save(connection, doc, "WORKFLOW_REVISED")
            return json_snapshot(doc)

    def confirm(self, workflow_id: str, *, expected_revision: int,
                confirmation_method: str) -> dict:
        if confirmation_method not in ("explicit_request", "followup"):
            raise ValueError("explicit confirmation method required")
        return self.revise(workflow_id, expected_revision=expected_revision,
                           confirmation_method=confirmation_method)

    def create_work(self, workflow_id: str, *, expected_revision: int,
                    idempotency_key: str | None = None) -> dict:
        if idempotency_key is not None:
            required(idempotency_key, "idempotency_key")
        at = self._now()
        with self.store.transaction() as connection:
            doc = self.store.load(connection, workflow_id)
            workflow = self._workflow(doc)
            if type(expected_revision) is not int or expected_revision != workflow["revision"]:
                raise ValueError("stale workflow revision")
            if workflow["confirmation"] is None:
                raise ValueError("explicit workflow confirmation required")
            confirmed = ConfirmedDelivery.from_dict(workflow["confirmation"])
            ConfirmedDelivery(confirmed.offer, confirmed.delivery, at, "followup")
            context = {"schema_version": 1, "source_workflow_id": workflow_id,
                           "source_task_id": workflow["source_task_id"],
                           "workflow_revision": workflow["revision"],
                           "confirmation_type": "confirmed_delivery_v1",
                           "intent": {"file": "collect", "link": "deliver_link",
                                   "both": "collect_and_link"}[confirmed.delivery.mode],
                           "confirmation": workflow["confirmation"]}
            key = idempotency_key or "workflow:" + _digest(context)
            existing = self.store.by_key(connection, key)
            if existing is not None and existing.get("workflow_context") != context:
                raise ValueError("idempotency key conflicts with another workflow context")
            if workflow["work_task_id"]:
                child = self.store.load(connection, workflow["work_task_id"])
                if existing is None or existing["task_id"] != child["task_id"]:
                    raise ValueError("work already linked under another idempotency key")
                return child
            if existing is not None:
                raise ValueError("workflow work linkage is inconsistent")
            child = self.store.document(confirmed.offer.request.text, at.isoformat())
            child["workflow_context"] = context
            self.store.insert(connection, child, key)
            self.store.event(connection, child["task_id"], {
                "kind": "TASK_CREATED", "at": at.isoformat(), "task_status": "CREATED",
                "source_workflow_id": workflow_id,
            })
            workflow.update(work_task_id=child["task_id"], state="WORK_CREATED")
            self._save(connection, doc, "WORKFLOW_WORK_LINKED")
            return json_snapshot(child)


def validate_workflow_task(store, connection, doc, at: datetime, *, allow_link: bool = False) -> None:
    """Validate only opt-in workflow records; legacy task contracts stay untouched."""
    if "workflow_request" in doc:
        raise ValueError("workflow request containers cannot execute")
    context = doc.get("workflow_context")
    if context is None:
        return
    if (context.get("schema_version") != 1
            or context.get("confirmation_type") != "confirmed_delivery_v1"):
        raise ValueError("unsupported workflow context")
    source = store.load(connection, context["source_workflow_id"])
    workflow = WorkflowService._workflow(source)
    if (workflow["revision"] != context["workflow_revision"]
            or workflow["work_task_id"] != doc["task_id"]
            or workflow["confirmation"] != context["confirmation"]
            or workflow["source_task_id"] != context["source_task_id"]):
        raise ValueError("workflow confirmation invalidated")
    confirmed = ConfirmedDelivery.from_dict(context["confirmation"])
    values = _restore(workflow["draft"])
    offer = DeliveryOffer(**{key: value for key, value in values.items() if key != "delivery"})
    if not confirmed.matches(offer, values["delivery"]):
        raise ValueError("workflow confirmation does not match current conditions")
    ConfirmedDelivery(offer, values["delivery"], at, "followup")
    expected = {"file": "collect", "link": "deliver_link", "both": "collect_and_link"}
    if context["intent"] != expected[confirmed.delivery.mode]:
        raise ValueError("workflow intent mismatch")
    if confirmed.delivery.mode == "link" and not allow_link:
        raise ValueError("link-only work requires a delivery handler, not a collector plan")
