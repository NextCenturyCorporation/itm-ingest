import argparse
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from decouple import config
from pymongo import MongoClient


DEFAULT_DB_NAME = "dashboard"
DEFAULT_COLLECTION_NAME = "admTargetRuns"
DEFAULT_KDMAS = ("affiliation", "merit", "search", "personal_safety")
DEFAULT_KDMA_ALIASES = {
    "AF": "affiliation",
    "MF": "merit",
    "PS": "personal_safety",
    "SS": "search",
}
TARGET_FIELDS = (
    ("evaluation.alignment_target_id", ("evaluation", "alignment_target_id")),
    ("alignment_target", ("alignment_target",)),
)
INVALID_KDMA_NAME = "<invalid>"
MISSING_KDMAS = "<missing>"
EMPTY_KDMAS = "<empty>"
UNKNOWN_TARGET = "<unknown>"
NOT_REQUESTED_ALIGNMENT_SCORE = "Not requested"
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def build_query(target_prefix: Optional[str] = None, domain: Optional[str] = None) -> Dict[str, Any]:
    target_clauses = []

    if target_prefix:
        target_regex = f"^{re.escape(target_prefix)}"
        for field_name, _ in TARGET_FIELDS:
            target_clauses.append({field_name: {"$regex": target_regex}})
    else:
        for field_name, _ in TARGET_FIELDS:
            target_clauses.append({field_name: {"$exists": True}})

    query: Dict[str, Any] = {"$or": target_clauses}

    if domain:
        query["evaluation.domain"] = domain

    return query


def get_nested_value(doc: Dict[str, Any], path: Sequence[str]) -> Any:
    current: Any = doc
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def get_target_candidates(doc: Dict[str, Any]) -> List[Tuple[str, str]]:
    candidates = []
    for field_name, path in TARGET_FIELDS:
        value = get_nested_value(doc, path)
        if isinstance(value, str) and value:
            candidates.append((field_name, value))
    return candidates


def normalize_observed_kdma(kdma_name: Any, alias_map: Dict[str, str]) -> str:
    if kdma_name is None:
        return INVALID_KDMA_NAME
    if not isinstance(kdma_name, str):
        return str(kdma_name)
    return alias_map.get(kdma_name.upper(), kdma_name)


def parse_alias_token(token: str, alias_map: Dict[str, str]) -> Optional[str]:
    match = re.fullmatch(r"([A-Za-z]+)\d*", token)
    if not match:
        return None
    return alias_map.get(match.group(1).upper())


def tokenize_full_name_segment(segment: str, allowed_kdmas: Sequence[str]) -> Optional[List[str]]:
    allowed_by_parts = {
        tuple(kdma.split("_")): kdma
        for kdma in sorted(allowed_kdmas, key=lambda value: len(value.split("_")), reverse=True)
    }
    segment_parts = segment.split("_")
    memo: Dict[int, Optional[List[str]]] = {}

    def parse_from(index: int) -> Optional[List[str]]:
        if index == len(segment_parts):
            return []
        if index in memo:
            return memo[index]

        for kdma_parts, kdma in allowed_by_parts.items():
            end = index + len(kdma_parts)
            if tuple(segment_parts[index:end]) != kdma_parts:
                continue
            rest = parse_from(end)
            if rest is not None:
                memo[index] = [kdma] + rest
                return memo[index]

        memo[index] = None
        return None

    return parse_from(0)


def parse_target_id(
    target_id: Any,
    allowed_kdmas: Sequence[str],
    alias_map: Dict[str, str],
) -> Optional[Tuple[str, Set[str]]]:
    if not isinstance(target_id, str):
        return None

    if UUID_PATTERN.fullmatch(target_id):
        return None

    parts = target_id.split("-")
    if len(parts) < 3:
        return None

    for index in range(1, len(parts)):
        expected: List[str] = []
        consumed_any = False

        for segment in parts[index:]:
            if segment in allowed_kdmas:
                expected.append(segment)
                consumed_any = True
                continue

            full_name_tokens = tokenize_full_name_segment(segment, allowed_kdmas)
            if full_name_tokens:
                expected.extend(full_name_tokens)
                consumed_any = True
                continue

            alias_kdma = parse_alias_token(segment, alias_map)
            if alias_kdma:
                expected.append(alias_kdma)
                consumed_any = True
                continue

            break

        if consumed_any:
            return "-".join(parts[:index]), set(expected)

    return None


def choose_parseable_target(
    doc: Dict[str, Any],
    allowed_kdmas: Sequence[str],
    alias_map: Dict[str, str],
) -> Tuple[Optional[str], Optional[str], Optional[Set[str]]]:
    for field_name, target_id in get_target_candidates(doc):
        parsed = parse_target_id(target_id, allowed_kdmas, alias_map)
        if parsed:
            target_prefix, expected_kdmas = parsed
            return field_name, target_id, expected_kdmas

    return None, None, None


def get_kdma_names(kdmas: Any, alias_map: Dict[str, str]) -> List[str]:
    if not isinstance(kdmas, list):
        return []
    return [
        normalize_observed_kdma(entry.get("kdma") if isinstance(entry, dict) else entry, alias_map)
        for entry in kdmas
    ]


def compare_kdmas(kdmas: Any, expected_kdmas: Set[str], alias_map: Dict[str, str]) -> Tuple[bool, List[str], List[str], str]:
    if kdmas is None:
        return True, sorted(expected_kdmas), [], "missing_results_kdmas"

    if not isinstance(kdmas, list):
        return True, sorted(expected_kdmas), [INVALID_KDMA_NAME], "invalid_results_kdmas"

    if not kdmas:
        return True, sorted(expected_kdmas), [], "empty_results_kdmas"

    observed_kdmas = get_kdma_names(kdmas, alias_map)
    observed_set = set(observed_kdmas)
    missing = sorted(expected_kdmas - observed_set)
    extra = sorted(observed_set - expected_kdmas)

    if missing and extra:
        return True, missing, extra, "missing_and_extra_kdma"
    if missing:
        return True, missing, [], "missing_kdma"
    if extra:
        return True, [], extra, "extra_kdma"

    return False, [], [], "ok"


def get_scenario_id(doc: Dict[str, Any]) -> Any:
    evaluation = doc.get("evaluation", {}) or {}
    return evaluation.get("scenario_id") or doc.get("scenario")


def is_not_requested_result(doc: Dict[str, Any]) -> bool:
    results = doc.get("results", {})
    if not isinstance(results, dict):
        return False
    return results.get("alignment_score") == NOT_REQUESTED_ALIGNMENT_SCORE and results.get("kdmas") is None


def is_open_world_doc(doc: Dict[str, Any]) -> bool:
    eval_name = doc.get("evalName") or doc.get("evaluation", {}).get("evalName")
    scenario_id = get_scenario_id(doc)

    if isinstance(eval_name, str) and "open world" in eval_name.lower():
        return True
    if isinstance(scenario_id, str) and ("OW_" in scenario_id or "openworld" in scenario_id.lower()):
        return True
    return bool(doc.get("openWorld"))


def print_suspicious_doc(
    doc: Dict[str, Any],
    target_field: str,
    target_id: str,
    expected_kdmas: Set[str],
    observed_kdmas: List[str],
    reason: str,
) -> None:
    print(
        "  "
        f"_id={doc.get('_id')} | "
        f"scenario_id={get_scenario_id(doc)} | "
        f"target_field={target_field} | "
        f"target_id={target_id} | "
        f"expected_kdmas={sorted(expected_kdmas)} | "
        f"observed_kdmas={observed_kdmas} | "
        f"reason={reason}"
    )


def find_suspicious_documents(
    collection: Any,
    target_prefix: Optional[str] = None,
    domain: Optional[str] = None,
    allowed_kdmas: Sequence[str] = DEFAULT_KDMAS,
    alias_map: Optional[Dict[str, str]] = None,
    include_not_requested: bool = False,
    include_open_world: bool = False,
) -> Tuple[int, int, int, int, int, Counter]:
    alias_map = alias_map or DEFAULT_KDMA_ALIASES
    query = build_query(target_prefix=target_prefix, domain=domain)
    projection = {
        "evaluation.scenario_id": 1,
        "evaluation.evalName": 1,
        "evaluation.alignment_target_id": 1,
        "evaluation.domain": 1,
        "evalName": 1,
        "alignment_target": 1,
        "scenario": 1,
        "openWorld": 1,
        "results.alignment_score": 1,
        "results.kdmas": 1,
    }

    matched = 0
    skipped_unparseable_target = 0
    skipped_not_requested = 0
    skipped_open_world = 0
    suspicious = 0
    summary: Counter = Counter()

    cursor = collection.find(query, projection=projection, batch_size=500)

    for doc in cursor:
        matched += 1

        target_field, target_id, expected_kdmas = choose_parseable_target(doc, allowed_kdmas, alias_map)
        if not target_id or not expected_kdmas:
            skipped_unparseable_target += 1
            continue

        if not include_not_requested and is_not_requested_result(doc):
            skipped_not_requested += 1
            continue

        if not include_open_world and is_open_world_doc(doc):
            skipped_open_world += 1
            continue

        target_prefix_value = parse_target_id(target_id, allowed_kdmas, alias_map)[0]
        results_kdmas = doc.get("results", {}).get("kdmas")
        is_suspicious, missing_kdmas, extra_kdmas, reason = compare_kdmas(results_kdmas, expected_kdmas, alias_map)

        if not is_suspicious:
            continue

        suspicious += 1
        observed_kdmas = get_kdma_names(results_kdmas, alias_map)
        print_suspicious_doc(doc, target_field, target_id, expected_kdmas, observed_kdmas, reason)

        if missing_kdmas:
            for missing_kdma in missing_kdmas:
                summary[(target_prefix_value, "missing", missing_kdma)] += 1
        if extra_kdmas:
            for extra_kdma in extra_kdmas:
                summary[(target_prefix_value, "extra", extra_kdma)] += 1

    return matched, skipped_unparseable_target, skipped_not_requested, skipped_open_world, suspicious, summary


def print_grouped_summary(summary: Counter) -> None:
    if not summary:
        print("Grouped summary: none")
        return

    print("Grouped summary by target prefix, issue type, and KDMA:")
    for (target_prefix, issue_type, kdma), count in sorted(summary.items()):
        print(f"  target_prefix={target_prefix} | issue={issue_type} | kdma={kdma} | count={count}")


def parse_allowed_kdmas(raw_values: Optional[List[str]]) -> Tuple[str, ...]:
    if not raw_values:
        return DEFAULT_KDMAS

    kdmas = []
    for raw_value in raw_values:
        for kdma in raw_value.split(","):
            clean = kdma.strip()
            if clean:
                kdmas.append(clean)

    return tuple(dict.fromkeys(kdmas))


def parse_aliases(raw_values: Optional[List[str]]) -> Dict[str, str]:
    alias_map = dict(DEFAULT_KDMA_ALIASES)
    if not raw_values:
        return alias_map

    for raw_value in raw_values:
        for pair in raw_value.split(","):
            if not pair.strip():
                continue
            if "=" not in pair:
                raise ValueError(f"Invalid alias {pair!r}; expected ALIAS=kdma_name.")
            alias, kdma = pair.split("=", 1)
            alias_map[alias.strip().upper()] = kdma.strip()

    return alias_map


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only detector for mismatches between target-implied KDMAs and results.kdmas."
    )
    parser.add_argument(
        "--mongo-url",
        default=None,
        help="Mongo connection URL. Defaults to MONGO_URL from .env/environment.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_NAME,
        help=f"Mongo database name. Default: {DEFAULT_DB_NAME}",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help=f"Mongo collection name. Default: {DEFAULT_COLLECTION_NAME}",
    )
    parser.add_argument(
        "--target-prefix",
        default=None,
        help="Optional target prefix filter, for example ADEPT-June2025 or Feb2026.",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Optional evaluation.domain filter, for example p2triage.",
    )
    parser.add_argument(
        "--kdma",
        action="append",
        default=None,
        help=(
            "Allowed KDMA name. May be repeated or comma-separated. "
            f"Default: {','.join(DEFAULT_KDMAS)}"
        ),
    )
    parser.add_argument(
        "--alias",
        action="append",
        default=None,
        help=(
            "KDMA target alias mapping, formatted ALIAS=kdma_name. May be repeated or comma-separated. "
            "Defaults: AF=affiliation, MF=merit, PS=personal_safety, SS=search."
        ),
    )
    parser.add_argument(
        "--include-not-requested",
        action="store_true",
        help=(
            "Include documents whose results explicitly say alignment was not requested. "
            "By default these are skipped because results.kdmas is expected to be null."
        ),
    )
    parser.add_argument(
        "--include-open-world",
        action="store_true",
        help=(
            "Include open-world documents. By default these are skipped because results.kdmas "
            "may store the full computed profile rather than only the target KDMA set."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mongo_url = args.mongo_url or config("MONGO_URL")
    allowed_kdmas = parse_allowed_kdmas(args.kdma)
    alias_map = parse_aliases(args.alias)

    print("Starting KDMA result-set consistency check.")
    print(f"Database: {args.db}")
    print(f"Collection: {args.collection}")
    print(f"Target prefix filter: {args.target_prefix or '<none>'}")
    print(f"Domain filter: {args.domain or '<none>'}")
    print(f"Include not-requested results: {args.include_not_requested}")
    print(f"Include open-world results: {args.include_open_world}")
    print(f"Allowed KDMAs: {list(allowed_kdmas)}")
    print(f"KDMA aliases: {alias_map}")
    print(f"Query: {build_query(target_prefix=args.target_prefix, domain=args.domain)}")

    client = MongoClient(mongo_url)
    try:
        collection = client[args.db][args.collection]
        (
            matched,
            skipped_unparseable_target,
            skipped_not_requested,
            skipped_open_world,
            suspicious,
            summary,
        ) = find_suspicious_documents(
            collection,
            target_prefix=args.target_prefix,
            domain=args.domain,
            allowed_kdmas=allowed_kdmas,
            alias_map=alias_map,
            include_not_requested=args.include_not_requested,
            include_open_world=args.include_open_world,
        )
    finally:
        client.close()

    print_grouped_summary(summary)
    print(
        "Summary: "
        f"matched={matched}, "
        f"suspicious={suspicious}, "
        f"skipped_unparseable_target={skipped_unparseable_target}, "
        f"skipped_not_requested={skipped_not_requested}, "
        f"skipped_open_world={skipped_open_world}"
    )

    if suspicious:
        print("KDMA result-set mismatches found.")
        return 1

    print("All parseable target-implied KDMA sets match results.kdmas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
