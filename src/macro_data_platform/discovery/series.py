"""Bounded metadata search and evidence-bound handoff to the existing workflow service."""
from __future__ import annotations

import re
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from uuid import uuid4

from macro_data_platform.mapping.concepts import concept_search_policy
from macro_data_platform.metadata.models import MetadataRecord, digest
from macro_data_platform.orchestration.workflow import WorkflowService
from macro_data_platform.storage.metadata import MetadataStore
from macro_data_platform.workflow_contracts import CandidateProposal, DataRequest
from macro_data_platform.workflow_extensions import (
    CandidateGroup,
    CandidateVariant,
    DataLink,
    DeliveryOffer,
    DeliverySpec,
    GroupedProposal,
    VariantAttributes,
    link_target_fingerprint,
)

INSTITUTION_IDS = {
    "worldbank": ("worldbank", "INT-04"), "imf": ("imf", "INT-01"),
    "tic": ("tic", "US-03"), "bis": ("bis", "INT-02"), "ecb": ("ecb", "EU-01"),
    "eurostat": ("eurostat", "EU-02"), "bea": ("bea", "US-04"),
    "fred": ("fred", "US-02"), "oecd": ("oecd", "INT-03"),
}


def _records(metadata, hint):
    if hint is None:
        return metadata.current_records(validate_structures=False)
    records = tuple(record for identifier in INSTITUTION_IDS.get(hint, (hint,))
                    for record in metadata.current_records(institution_id=identifier,
                                                           validate_structures=False))
    if len(records) > 200:
        raise ValueError("metadata query budget exceeded")
    return records


def parse_request(text: str, request_id: str | None = None):
    """Small explicit bilingual vocabulary; unknown conditions remain questions."""
    folded = text.casefold()
    concepts = []
    for concept, terms in (
        ("gdp", ("gdp", "국내총생산")),
        ("portfolio_investment", ("portfolio investment", "포트폴리오 투자")),
        ("treasury_holdings", ("treasury holdings", "국채 보유", "국채보유")),
        ("treasury_transactions", ("treasury transactions", "국채 거래", "국채거래")),
    ):
        if any(term in folded for term in terms):
            concepts.append(concept)
    if "gdp" in concepts:
        gdp_concept = "gdp"
        if any(term in folded for term in ("gdp growth", "gdp 증가율", "gdp 성장률")):
            gdp_concept = "gdp_growth"
        elif any(term in folded for term in ("gdp per capita", "per capita gdp", "1인당 gdp")):
            gdp_concept = "gdp_per_capita"
        else:
            nominal = "명목" in folded or re.search(r"\bnominal\b", folded) is not None
            real = "실질" in folded or re.search(r"\breal\b", folded) is not None
            if nominal != real:
                gdp_concept = "gdp_nominal" if nominal else "gdp_real"
        concepts = [gdp_concept if value == "gdp" else value for value in concepts]
    institutions = [key for key, terms in (
        ("worldbank", ("world bank", "세계은행")),
        ("tic", ("tic", "미국 재무부")), ("imf", ("imf",)),
        ("fred", ("fred",)), ("bis", ("bis",)), ("ecb", ("ecb",)),
        ("eurostat", ("eurostat",)), ("bea", ("bea",)), ("oecd", ("oecd",)),
    ) if any(term in folded for term in terms)]
    geography_text = folded.replace("미국 재무부", "")
    countries = tuple(key for key, terms in (
        ("USA", ("미국", "united states", "usa")),
        ("JPN", ("일본", "japan", "jpn")), ("DEU", ("독일", "germany", "deu")),
    ) if any(term in geography_text for term in terms))
    periods = [v.upper() for v in re.findall(
        r"(?<!\d)(?:19|20)\d{2}(?:-(?:Q\d|\d{2}(?:-\d{2})?))?(?!\d)",
        text, re.IGNORECASE)]
    frequencies = [value for value, terms in (
        ("annual", ("annual", "연간")), ("monthly", ("monthly", "월별")),
        ("quarterly", ("quarterly", "분기")), ("source", ("원주기", "source frequency")),
        ("daily", ("daily", "일별")),
    ) if any(term in folded for term in terms)]
    request = DataRequest(
        request_id or uuid4().hex, text,
        concept=concepts[0] if len(concepts) == 1 else None,
        institution_hint=(institutions[0] if len(institutions) == 1 else
                          "unresolved:" + ",".join(institutions) if institutions else None),
        countries=countries,
        dimensions={} if "추가차원없음" in folded or "no extra dimensions" in folded else None,
        period_start=periods[0] if len(periods) == 2 else None,
        period_end=periods[1] if len(periods) == 2 else None,
        frequency=frequencies[0] if len(frequencies) == 1 else None,
        unit_policy="preserve" if "원단위 유지" in folded or "preserve units" in folded else None,
        vintage_requirement="latest_available" if "최신" in folded or "latest" in folded else None,
    )
    stock_flow = {"treasury_holdings": "stock", "treasury_transactions": "flow"}.get(request.concept)
    return request, VariantAttributes(stock_flow=stock_flow)


@dataclass(frozen=True)
class SearchOutcome:
    request: DataRequest
    proposal: GroupedProposal
    records: tuple[MetadataRecord, ...]
    rejections: tuple[dict, ...]
    reviews: dict[str, tuple[str, ...]]
    questions: tuple[dict, ...]
    requested_scope: str | None
    accepted_scope: str | None
    requirements: VariantAttributes
    concept_matches: dict[str, dict]
    related_candidates: tuple[dict, ...]


def _route(routes, record):
    supported = [route for route in routes if route.supports(record)]
    if len(supported) > 1:
        raise ValueError("multiple ingestion routes match the same source series")
    return supported[0] if supported else None


def _compatible(request, record, requirements, scope, accepted_scope, policy):
    candidate = record.candidate
    rejected, review = [], []
    concept_match = policy.match(request.concept, record.concept_id, record.attributes)
    review.extend(concept_match.reviews)
    if not concept_match.primary:
        rejected.append("concept_mismatch_or_unmapped")
    if request.countries and not set(request.countries).issubset(candidate.countries):
        rejected.append("country_coverage_mismatch")
    if request.dimensions is not None:
        if candidate.dimensions is None:
            review.append("dimensions_unknown")
        elif set(request.dimensions) != set(candidate.dimensions) or any(
            not set(values).issubset(candidate.dimensions.get(name, ()))
            for name, values in request.dimensions.items()
        ):
            rejected.append("dimension_mismatch")
    if request.frequency not in (None, "source"):
        if candidate.frequency is None:
            review.append("frequency_unknown")
        elif request.frequency != candidate.frequency:
            rejected.append("frequency_mismatch")
    if request.period_start and request.period_end:
        from macro_data_platform.workflow_contracts import _period
        if candidate.available_start is None or candidate.available_end is None:
            review.append("period_coverage_unknown")
        else:
            first, last = _period(candidate.available_start), _period(candidate.available_end)
            start, end = _period(request.period_start), _period(request.period_end)
            if first[0] != start[0] or last[0] != end[0] or not first <= start <= end <= last:
                rejected.append("period_coverage_mismatch")
    for attribute in fields(requirements):
        expected = getattr(requirements, attribute.name)
        actual = getattr(record.attributes, attribute.name)
        if attribute.name == "source_codes":
            if any(actual.get(k) != v for k, v in expected.items()):
                rejected.append("variant_source_code_mismatch")
        elif expected is not None:
            if actual is None:
                review.append("variant_unknown:" + attribute.name)
            elif expected != actual:
                rejected.append("variant_mismatch:" + attribute.name)
    if scope is not None and record.scope != scope:
        relation = next((r for r in record.scope_relations if r.target == scope), None)
        if relation is None or relation.relation == "unknown":
            review.append("source_scope_uncertain")
        elif relation.relation == "broader":
            if accepted_scope != record.scope:
                review.append("broader_scope_requires_acceptance")
        elif relation.relation == "exact":
            pass
        else:
            rejected.append("source_scope_" + relation.relation)
    return rejected, review, concept_match


class SeriesDiscoveryService:
    def __init__(self, metadata: MetadataStore, history, routes=(), *,
                 clock=lambda: datetime.now(UTC)):
        if metadata.settings.database_path != history.settings.database_path:
            raise ValueError("metadata and history must use the same database")
        self.metadata, self.history, self.routes, self.clock = metadata, history, tuple(routes), clock
        self.workflow = WorkflowService(history, clock=lambda: self.clock())

    def search(self, request: DataRequest, *, requirements=None, requested_scope=None,
               accepted_scope=None):
        requirements = requirements or VariantAttributes(stock_flow={
            "treasury_holdings": "stock", "treasury_transactions": "flow",
        }.get(request.concept))
        policy = concept_search_policy()
        query_facets = policy.query_facets(request.concept)
        if any(getattr(requirements, name) not in (None, value)
               for name, value in query_facets.items()):
            raise ValueError("query subtype and explicit variant requirements conflict")
        requirements = replace(requirements, **query_facets)
        records = _records(self.metadata, request.institution_hint)
        matched, rejected, reviews, candidates = [], [], {}, []
        concept_matches, related = {}, []
        for record in records:
            reasons, review, concept_match = _compatible(
                request, record, requirements, requested_scope, accepted_scope, policy)
            if reasons:
                rejected.append({"candidate_id": record.candidate.candidate_id,
                                 "reasons": reasons})
                nonconcept_reasons = [reason for reason in reasons
                                      if reason != "concept_mismatch_or_unmapped"]
                if concept_match.relation == "related" and not nonconcept_reasons:
                    related.append({"candidate": {
                        "candidate_id": record.candidate.candidate_id,
                        "institution_id": record.candidate.institution_id,
                        "metadata_revision": record.candidate.metadata_revision,
                        "label": record.candidate.label[:256],
                        "label_truncated": len(record.candidate.label) > 256,
                    },
                                    "concept_match": concept_match.to_dict()})
                continue
            concept_matches[record.candidate.candidate_id] = concept_match.to_dict()
            if request.concept is None:
                review.append("requested_concept_unknown")
            try:
                self.metadata.validate_structure(record)
            except ValueError:
                review.append("source_structure_invalid")
            route = _route(self.routes, record)
            supported = (route is not None and route.available(record, self.clock())
                         and request.unit_policy != "convert"
                         and request.vintage_requirement in (None, "latest_available")
                         and "source_structure_invalid" not in review)
            candidate = replace(record.candidate,
                                support_status="supported" if supported else "unsupported",
                                supported_outputs=(
                                    route.formats_for(record) if hasattr(route, "formats_for")
                                    else route.formats
                                ) if supported else (),
                                rationale=concept_match.reason,
                                uncertainties=tuple(sorted(set(record.candidate.uncertainties) |
                                                           set(review))))
            matched.append(record)
            candidates.append(candidate)
            reviews[candidate.candidate_id] = tuple(review)
        order = sorted(range(len(candidates)),
                       key=lambda i: (len(reviews[candidates[i].candidate_id]),
                                      candidates[i].candidate_id))
        candidates = tuple(candidates[i] for i in order)
        matched = tuple(matched[i] for i in order)
        proposal = CandidateProposal(
            digest({"request": request.to_dict(),
                    "records": [r.to_dict() for r in matched],
                    "requirements": requirements.to_dict(), "scope": requested_scope,
                    "accepted_scope": accepted_scope, "concept_policy": policy.fingerprint}),
            request.request_id, 1, self.clock(), candidates,
        )
        variants = tuple(CandidateVariant(
            r.candidate.candidate_id, concept_matches[r.candidate.candidate_id]["family_id"]
            or "unmapped:" + r.candidate.candidate_id,
            r.attributes, r.candidate.evidence,
        ) for r in matched)
        groups = {}
        for record in matched:
            # Stock/flow, level/change, definition and scope differences cannot be hidden in a group.
            family = concept_matches[record.candidate.candidate_id]["family_id"]
            key = (family, policy.group_definition(family, record.candidate.definition), record.scope,
                   record.attributes.stock_flow, record.attributes.measure)
            groups.setdefault(key, []).append(record)
        grouped = tuple(CandidateGroup(
            digest({"key": key, "members": [r.candidate.candidate_id for r in members]}),
            key[0],
            tuple(r.candidate.candidate_id for r in members),
            "Reviewed search-family membership; definitions and variant differences retained",
            tuple({e.evidence_id: e for r in members for e in r.candidate.evidence}.values()),
        ) for key, members in groups.items() if key[0] is not None and len(members) > 1)
        questions = []
        if request.concept is None:
            questions.append({"field": "concept", "kind": "input", "choices": []})
        if len(matched) > 1:
            for field in ("seasonal_adjustment", "price_basis", "measure", "stock_flow", "population"):
                choices = {getattr(r.attributes, field) for r in matched}
                if len(choices) > 1 and getattr(requirements, field) is None:
                    questions.append({"field": "variant." + field, "kind": "input",
                                      "choices": sorted(c for c in choices if c is not None)})
        for name in policy.choice_fields(request.concept):
            if matched and getattr(requirements, name) is None:
                choices = {getattr(r.attributes, name) for r in matched}
                question = {"field": "variant." + name,
                            "kind": "review" if None in choices else "input",
                            "choices": sorted(v for v in choices if v is not None)}
                questions = [q for q in questions if q["field"] != question["field"]]
                questions.append(question)
        return SearchOutcome(request, GroupedProposal(proposal, variants, grouped), matched,
                             tuple(rejected), reviews, tuple(questions), requested_scope,
                             accepted_scope, requirements, concept_matches, tuple(related))

    def _links(self, outcome, candidate_id):
        record = next(r for r in outcome.records if r.candidate.candidate_id == candidate_id)
        access = record.access
        if access is None:
            return ()
        status = access.status
        if status == "available" and (not access.shareable or
                                      record.candidate.auth_requirement != "none"):
            status = "blocked"
        checked_at = access.checked_at
        if checked_at is not None and any(
            evidence.retrieved_at > checked_at for evidence in record.candidate.evidence
        ):
            status, checked_at = "unknown", None
        return (DataLink(
            digest({"candidate": candidate_id, "revision": record.candidate.metadata_revision}),
            candidate_id, outcome.proposal.proposal.proposal_id, 1,
            link_target_fingerprint(outcome.request, outcome.proposal, candidate_id,
                                    outcome.requirements),
            status=status, url=access.url, kind="download",
            checked_at=checked_at, expires_at=access.expires_at, official=True,
            shareable=access.shareable,
            access_requirement="public" if record.candidate.auth_requirement == "none"
            else "authentication_required", manual_filter_required=access.manual_filter_required,
            reason="Supplied metadata evidence; no live link check",
            evidence=record.candidate.evidence,
        ),)

    def offer(self, outcome, candidate_id):
        return DeliveryOffer(outcome.request, outcome.proposal, candidate_id,
                             outcome.requirements, self._links(outcome, candidate_id))

    def _attach(self, doc, outcome):
        selected = doc["workflow_request"]["draft"]["candidate_id"]
        blockers = list(outcome.reviews.get(selected, ()))
        questions = list(outcome.questions) if selected is None else []
        questions += [{"field": "meaning." + b, "kind": "review", "choices": []} for b in blockers]
        unresolved_concept = outcome.request.concept is None
        if not outcome.records and not unresolved_concept:
            questions.append({"field": "discovery.no_candidates", "kind": "review", "choices": []})
        context = {
            "schema_version": 1,
            "basis": {r.candidate.candidate_id: digest(r.to_dict()) for r in outcome.records},
            "institution_hint": outcome.request.institution_hint,
            "requested_scope": outcome.requested_scope, "accepted_scope": outcome.accepted_scope,
            "requirements": outcome.requirements.to_dict(),
            "reviews": {k: list(v) for k, v in outcome.reviews.items()},
            "rejections": list(outcome.rejections),
            "concept_policy_fingerprint": concept_search_policy().fingerprint,
            "concept_matches": outcome.concept_matches,
            "related_candidates": list(outcome.related_candidates),
            "proposal_fingerprint": digest(outcome.proposal.to_dict()),
            "request_fingerprint": digest(outcome.request.to_dict()),
        }
        with self.history.transaction() as db:
            current = self.history.load(db, doc["task_id"])
            current["discovery_context"] = context
            if questions:
                workflow = current["workflow_request"]
                workflow["questions"] += [q for q in questions if q not in workflow["questions"]]
                workflow["state"] = ("NEEDS_REVIEW" if blockers or
                                     (not outcome.records and not unresolved_concept) or
                                     any(q["kind"] == "review" for q in questions) else "NEEDS_INPUT")
                workflow["confirmation"] = None
            self.history.save(db, current)
            self.history.event(db, current["task_id"], {
                "kind": "DISCOVERY_ASSESSED", "at": self.clock().isoformat(), "snapshot": context,
            })
        return self.history.get(doc["task_id"])

    def begin(self, request, *, candidate_id=None, delivery=None, confirmation_method=None,
              requirements=None, requested_scope=None, accepted_scope=None):
        if isinstance(request, str):
            request, parsed_requirements = parse_request(request)
            requirements = requirements or parsed_requirements
        if accepted_scope is not None and confirmation_method not in {"explicit_request", "followup"}:
            raise ValueError("scope acceptance requires an explicit user instruction")
        if accepted_scope is not None and requested_scope is None:
            raise ValueError("scope acceptance needs the original requested scope")
        outcome = self.search(request, requirements=requirements, requested_scope=requested_scope,
                              accepted_scope=accepted_scope)
        if (candidate_id is None and len(outcome.records) == 1 and
                confirmation_method is not None and not outcome.questions):
            candidate_id = outcome.records[0].candidate.candidate_id
        if candidate_id is not None and candidate_id not in outcome.reviews:
            raise ValueError("selected candidate is not present in the current search")
        links = self._links(outcome, candidate_id) if candidate_id else ()
        blockers = outcome.reviews.get(candidate_id, ())
        doc = self.workflow.begin(
            request, outcome.proposal, candidate_id=candidate_id,
            delivery=delivery or DeliverySpec(), links=links, requirements=outcome.requirements,
            confirmation_method=confirmation_method if not blockers else None,
        )
        return self._attach(doc, outcome)

    def revise(self, workflow_id, *, expected_revision, request=None, candidate_id=None,
               delivery=None, requirements=None, accepted_scope=None, confirmation_method=None):
        source = self.history.get(workflow_id)
        context, workflow = source["discovery_context"], source["workflow_request"]
        if expected_revision != workflow["revision"]:
            raise ValueError("stale workflow revision")
        if accepted_scope is not None and confirmation_method not in {"explicit_request", "followup"}:
            raise ValueError("scope acceptance requires an explicit user instruction")
        if accepted_scope is not None and context["requested_scope"] is None:
            raise ValueError("scope acceptance needs the original requested scope")
        previous_request = DataRequest.from_dict(workflow["draft"]["request"])
        request = request or previous_request
        concept_changed = request.concept != previous_request.concept
        if requirements is None:
            requirements = VariantAttributes.from_dict(context["requirements"])
            if concept_changed:
                policy = concept_search_policy()
                changes = {name: None for name in policy.query_facets(previous_request.concept)}
                changes.update(policy.query_facets(request.concept))
                if previous_request.concept in {"treasury_holdings", "treasury_transactions"}:
                    changes["stock_flow"] = None
                if request.concept in {"treasury_holdings", "treasury_transactions"}:
                    changes["stock_flow"] = (
                        "stock" if request.concept == "treasury_holdings" else "flow")
                requirements = replace(requirements, **changes)
        outcome = self.search(
            request, requirements=requirements,
            requested_scope=context["requested_scope"],
            accepted_scope=accepted_scope or context["accepted_scope"],
        )
        previous = GroupedProposal.from_dict(workflow["draft"]["proposal"])
        stable = replace(outcome.proposal, proposal=replace(
            outcome.proposal.proposal, created_at=previous.proposal.created_at))
        if stable == previous:
            outcome = replace(outcome, proposal=previous)
        selected = candidate_id if candidate_id is not None else (
            None if concept_changed else workflow["draft"]["candidate_id"])
        if selected not in outcome.reviews:
            if candidate_id is not None:
                raise ValueError("selected candidate is not present in the current search")
            selected = None
        if (selected is None and len(outcome.records) == 1 and confirmation_method is not None
                and not outcome.questions):
            selected = outcome.records[0].candidate.candidate_id
        links = self._links(outcome, selected) if selected else ()
        doc = self.workflow.revise(
            workflow_id, expected_revision=expected_revision, request=request,
            proposal=outcome.proposal, candidate_id=selected,
            links=links, delivery=delivery or DeliverySpec.from_dict(workflow["draft"]["delivery"]),
            requirements=outcome.requirements,
            confirmation_method=confirmation_method if not outcome.reviews.get(selected) else None,
        )
        return self._attach(doc, outcome)

    def create_work(self, workflow_id, *, expected_revision):
        source = self.history.get(workflow_id)
        validate_discovery_context(self.history, source)
        return self.workflow.create_work(workflow_id, expected_revision=expected_revision)

    def _run(self, task_id, *, resume=False, approved=False):
        child = self.history.get(task_id)
        source = self.history.get(child["workflow_context"]["source_workflow_id"])
        validate_discovery_context(self.history, source)
        if source["workflow_request"]["draft"]["delivery"]["mode"] == "link":
            if resume:
                raise ValueError("Link delivery has no collector attempt to resume")
            from macro_data_platform.ingestion.discovered import deliver_links
            return deliver_links(self.history, task_id, self.clock())
        selected = source["workflow_request"]["draft"]["candidate_id"]
        record = next(r for r in _records(
            self.metadata, source["discovery_context"]["institution_hint"])
            if r.candidate.candidate_id == selected)
        route = _route(self.routes, record)
        if route is None:
            raise ValueError("no ingestion route for selected candidate")
        dispatcher = route.dispatcher(self.history.settings, self.history, record, self.clock)
        if resume:
            return dispatcher.resume(task_id, approved=approved)
        return dispatcher.run(task_id)

    def run(self, task_id):
        return self._run(task_id)

    def resume(self, task_id, *, approved=False):
        return self._run(task_id, resume=True, approved=approved)


def validate_discovery_context(history, source):
    context = source.get("discovery_context")
    if context is None:
        return
    if context.get("schema_version") != 1:
        raise ValueError("unsupported discovery context")
    if context.get("concept_policy_fingerprint") != concept_search_policy().fingerprint:
        raise ValueError("concept search policy changed; search and confirm again")
    draft = source["workflow_request"]["draft"]
    if (context.get("proposal_fingerprint") != digest(draft["proposal"]) or
            context.get("request_fingerprint") != digest(draft["request"]) or
            context["requirements"] != draft["requirements"]):
        raise ValueError("discovery conditions changed outside search; search and confirm again")
    metadata = MetadataStore(history.settings, initialize=False)
    records = _records(metadata, context["institution_hint"])
    current = {r.candidate.candidate_id: digest(r.to_dict()) for r in records}
    if any(current.get(key) != value for key, value in context["basis"].items()):
        raise ValueError("discovered metadata changed; search and confirm again")
    selected = source["workflow_request"]["draft"]["candidate_id"]
    if selected is None or selected not in context["basis"] or context["reviews"].get(selected):
        raise ValueError("discovered candidate meaning requires review")
    metadata.validate_structure(next(r for r in records if r.candidate.candidate_id == selected))
