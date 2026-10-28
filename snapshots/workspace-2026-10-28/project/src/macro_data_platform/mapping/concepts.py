"""Versioned search inclusion rules. Membership never asserts statistical equivalence."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from types import MappingProxyType

from macro_data_platform.metadata.models import digest


@dataclass(frozen=True)
class ConceptLink:
    parent: str
    child: str
    relation: str
    reference: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.parent, self.child, self.reference)):
            raise ValueError("concept relations require identities and a reference")
        if self.parent == self.child or self.relation not in {"subtype", "related"}:
            raise ValueError("invalid concept relation")


@dataclass(frozen=True)
class ConceptMatch:
    query_concept: str | None
    source_concept: str | None
    family_id: str | None
    relation: str
    path: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    reviews: tuple[str, ...] = ()
    reason: str = ""

    @property
    def primary(self):
        return self.relation in {"exact_concept", "subtype", "family_variant"}

    def to_dict(self):
        return asdict(self)


class ConceptSearchPolicy:
    """Small reviewed graph, bounded traversal and explicit query facets."""
    def __init__(self, version, links=(), *, aliases=None, facets=None):
        if not isinstance(version, str) or not version:
            raise ValueError("concept policy requires a version")
        links = tuple(links)
        if len(links) > 64 or len({(v.parent, v.child) for v in links}) != len(links):
            raise ValueError("duplicate or excessive concept relations")
        self.version, self.links = version, links
        self.aliases = MappingProxyType(dict(aliases or {}))
        self.facets = MappingProxyType({
            key: MappingProxyType(dict(value)) for key, value in (facets or {}).items()
        })
        if any(value in self.aliases for value in self.aliases.values()):
            raise ValueError("concept aliases must be direct and acyclic")
        parents = {}
        for link in links:
            if link.relation == "subtype":
                if link.child in parents and parents[link.child] != link.parent:
                    raise ValueError("ambiguous search family parent")
                parents[link.child] = link.parent
        self.parents = MappingProxyType(parents)
        for node in parents:
            visited, current = set(), node
            while current in parents:
                if current in visited:
                    raise ValueError("cyclic subtype relation")
                visited.add(current)
                if len(visited) > 4:
                    raise ValueError("concept relation depth limit exceeded")
                current = parents[current]

    @property
    def fingerprint(self):
        return digest({
            "version": self.version, "links": [asdict(v) for v in self.links],
            "aliases": dict(self.aliases),
            "facets": {k: dict(v) for k, v in self.facets.items()},
        })

    def canonical(self, concept):
        return self.aliases.get(concept, concept)

    def family(self, concept):
        current = self.canonical(concept)
        while current in self.parents:
            current = self.parents[current]
        return current

    def query_facets(self, concept):
        return dict(self.facets.get(self.canonical(concept), {}))

    def choice_fields(self, concept):
        target = self.canonical(concept)
        if target != self.family(target):
            return ()
        return tuple(sorted({
            name for source, attributes in self.facets.items() if self.family(source) == target
            for name in attributes
        }))

    def group_definition(self, family, definition):
        return None if any(link.parent == family and link.relation == "subtype"
                           for link in self.links) else definition

    def _path(self, start, target):
        queue = deque([(start, (), ())])
        visited = set()
        while queue:
            current, path, refs = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            if len(visited) > 16:
                raise ValueError("concept expansion budget exceeded")
            if current == target:
                return (*path, current), refs
            for link in self.links:
                if link.relation == "subtype" and link.parent == current:
                    queue.append((link.child, (*path, current), (*refs, link.reference)))
        return (), ()

    def match(self, query, source, attributes):
        target, actual = self.canonical(query), self.canonical(source)
        family = self.family(target)
        if target is None:
            return ConceptMatch(query, source, None, "unmapped",
                                reviews=("requested_concept_unknown",),
                                reason="A concept must be clarified before source concepts can match")
        if actual is None:
            return ConceptMatch(query, source, family, "unmapped",
                                reason="No explicit source concept mapping")
        related = next((link for link in self.links if link.relation == "related"
                        and {link.parent, link.child} == {target, actual}), None)
        if related is not None:
            return ConceptMatch(query, source, family, "related",
                                references=(related.reference,),
                                reason="Related indicator; not a substitute for the requested measure")
        if self.family(actual) != family:
            return ConceptMatch(query, source, family, "unrelated",
                                reason="No reviewed search-family inclusion relation")
        query_facets, source_facets = self.query_facets(target), self.query_facets(actual)
        if any(name in source_facets and source_facets[name] != value
               for name, value in query_facets.items()):
            return ConceptMatch(query, source, family, "unrelated",
                                reason="Source subtype contradicts the requested subtype")
        if family == "gdp" and attributes.measure in {"change", "rate"}:
            return ConceptMatch(query, source, family, "related",
                                reason="Source measure differs from GDP level; identifier alone is insufficient")
        path, refs = self._path(family, actual)
        reviews = []
        for name, expected in source_facets.items():
            value = getattr(attributes, name)
            if value is None:
                reviews.append("concept_attribute_unknown:" + name)
            elif value != expected:
                reviews.append("concept_attribute_conflict:" + name)
        if family == "gdp" and attributes.price_basis is None:
            reviews.append("gdp_price_basis_unknown")
        elif family == "gdp" and attributes.price_basis not in {"nominal", "real"}:
            reviews.append("gdp_price_basis_unresolved")
        if family == "gdp" and attributes.measure == "index":
            reviews.append("gdp_index_measure_requires_context")
        if family == "gdp" and attributes.measure is None:
            reviews.append("gdp_measure_unknown")
        if family == "gdp" and attributes.stock_flow == "stock":
            reviews.append("gdp_stock_flow_conflict")
        if family == "gdp" and not refs:
            refs = (_REFERENCE,)
        relation = ("subtype" if target == family and actual != family else
                    "family_variant" if family == "gdp" or target != actual else "exact_concept")
        return ConceptMatch(
            query, source, family, relation, path, refs, tuple(sorted(set(reviews))),
            "Included through reviewed search family " + str(family) +
            "; source identity and statistical differences retained",
        )


_REFERENCE = "docs/developer/planning/CONCEPT_SEARCH_REVISION_PLAN.md#제품-정책"
DEFAULT_CONCEPT_POLICY = ConceptSearchPolicy(
    "gdp-family-2026-10-25-v1",
    (
        ConceptLink("gdp", "gdp_nominal", "subtype", _REFERENCE),
        ConceptLink("gdp", "gdp_real", "subtype", _REFERENCE),
        ConceptLink("gdp", "gdp_growth", "related", _REFERENCE),
        ConceptLink("gdp", "gdp_per_capita", "related", _REFERENCE),
    ),
    aliases={"nominal_gdp": "gdp_nominal", "real_gdp": "gdp_real"},
    facets={"gdp_nominal": {"price_basis": "nominal"}, "gdp_real": {"price_basis": "real"}},
)


def concept_search_policy():
    return DEFAULT_CONCEPT_POLICY
