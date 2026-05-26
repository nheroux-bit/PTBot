"""Two-pass orchestration for precedent transaction research."""

from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

from . import db as _db
from .models import AgentRunResult, AgentTask, DealCandidate, PipelinePaths, ResearchParams
from .prompt_builder import build_pass1_tasks, build_pass2_tasks, build_qc_prompt

Runner = Callable[[str, int], dict[str, Any]]


def load_attack_market_runner(orchestrator_path: Path | None = None) -> Runner:
    """Load attack.market's run_local_agent without modifying attack.market."""
    path = orchestrator_path or (
        Path.home() / ".agents" / "skills" / "attack.market" / "scripts" / "orchestrate.py"
    )
    if not path.exists():
        raise FileNotFoundError(f"attack.market orchestrator not found: {path}")
    spec = importlib.util.spec_from_file_location("attack_market_orchestrate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load attack.market orchestrator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runner = getattr(module, "run_local_agent", None)
    if not callable(runner):
        raise ImportError("attack.market orchestrator does not expose run_local_agent")
    return cast(Runner, runner)


def normalize_result(raw: dict[str, Any]) -> AgentRunResult:
    """Normalize the dict returned by attack.market into a validated result."""
    return AgentRunResult(
        state=str(raw.get("state", "UNKNOWN")),
        output=str(raw.get("output", "")),
        run_id=str(raw.get("run_id", "")),
        run_url=str(raw.get("run_url", "")),
        error=str(raw["error"]) if raw.get("error") else None,
    )


def run_tasks(tasks: list[AgentTask], runner: Runner, timeout: int) -> dict[str, AgentRunResult]:
    """Run tasks in parallel using the provided Oz runner."""
    results: dict[str, AgentRunResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        futures = {pool.submit(runner, task.prompt, timeout): task.id for task in tasks}
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                results[task_id] = normalize_result(future.result())
            except Exception as exc:  # noqa: BLE001 - boundary normalizes unknown runner errors
                results[task_id] = AgentRunResult(state="FAILED", output="", error=str(exc))
    return results


def extract_json_array(text: str) -> list[dict[str, Any]]:
    """Extract the first JSON array from an agent response."""
    stripped = text.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", stripped, re.DOTALL)
    if fenced:
        parsed = json.loads(fenced.group(1))
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start >= 0 and end > start:
        parsed = json.loads(stripped[start : end + 1])
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _normalize_deal_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Coerce agent-output deal fields to their expected types before validation.

    Agents return inconsistent types for several fields.  This normaliser
    fixes the most common mismatches without touching the frozen DealCandidate
    model:

    - deal_value / date: numeric or non-string → str
    - multiples_disclosed / computed_multiples_available: any non-bool.
      When a list is received in a bool field the agent has accidentally put
      multiples data there; the list is merged into the ``multiples`` field
      and the bool is set to True.
    """
    result = dict(item)

    # String fields that agents sometimes return as numbers
    for str_field in ("deal_value", "date"):
        val = result.get(str_field)
        if val is not None and not isinstance(val, str):
            result[str_field] = str(val)

    # Bool fields that agents sometimes return as lists of multiples strings
    for bool_field in ("multiples_disclosed", "computed_multiples_available"):
        val = result.get(bool_field)
        if val is None or isinstance(val, bool):
            continue
        if isinstance(val, list):
            # Merge the misplaced multiples into the multiples field
            existing = result.get("multiples") or []
            if isinstance(existing, (list, tuple)):
                merged = list(existing) + [str(v) for v in val if v]
            else:
                merged = [str(v) for v in val if v]
            result["multiples"] = merged
            result[bool_field] = True
        else:
            result[bool_field] = bool(val)

    return result


def candidates_from_results(results: dict[str, AgentRunResult]) -> list[DealCandidate]:
    """Parse deal candidates from all successful Pass 1 scout outputs."""
    candidates: list[DealCandidate] = []
    for result in results.values():
        if result.state != "SUCCEEDED":
            continue
        for item in extract_json_array(result.output):
            candidates.append(DealCandidate.model_validate(_normalize_deal_dict(item)))
    return candidates


def dedupe_deals(candidates: list[DealCandidate]) -> list[DealCandidate]:
    """Deduplicate candidates by normalized target/acquirer key."""
    deduped: dict[str, DealCandidate] = {}
    for candidate in candidates:
        existing = deduped.get(candidate.key())
        if existing is None:
            deduped[candidate.key()] = candidate
            continue
        merged_multiples = tuple(dict.fromkeys((*existing.multiples, *candidate.multiples)))
        merged_sources = tuple(dict.fromkeys((*existing.source_urls, *candidate.source_urls)))
        deduped[candidate.key()] = existing.model_copy(
            update={
                "multiples_disclosed": existing.multiples_disclosed
                or candidate.multiples_disclosed,
                "computed_multiples_available": existing.computed_multiples_available
                or candidate.computed_multiples_available,
                "multiples": merged_multiples,
                "source_urls": merged_sources,
                "deal_value": existing.deal_value or candidate.deal_value,
                "date": existing.date or candidate.date,
            }
        )
    return list(deduped.values())


def filter_qualified_deals(
    candidates: list[DealCandidate], min_multiples: int
) -> list[DealCandidate]:
    """Keep only deals satisfying the disclosed/computable multiples rule."""
    return [candidate for candidate in candidates if candidate.qualifies(min_multiples)]


def compile_agent_outputs(
    title: str, tasks: list[AgentTask], results: dict[str, AgentRunResult]
) -> str:
    """Compile task outputs into markdown."""
    sections = [f"# {title}"]
    for task in tasks:
        result = results.get(task.id)
        if result is None or result.state != "SUCCEEDED":
            error = result.error if result else "missing result"
            sections.append(f"## {task.label}\n\nStatus: FAILED\n\n{error}")
            continue
        sections.append(f"## {task.label}\n\n{result.output}")
    return "\n\n".join(sections)


def write_json(path: Path, payload: object) -> None:
    """Write pretty JSON to a path."""
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_pipeline(
    params: ResearchParams,
    output_dir: Path,
    *,
    runner: Runner | None = None,
    timeout: int = 900,
    db_path: Path | None = None,
) -> PipelinePaths:
    """Run the full two-pass pipeline and write markdown/JSON outputs."""
    active_runner = runner or load_attack_market_runner()
    supporting_dir = output_dir / "supporting"
    metadata_dir = output_dir / "metadata"
    supporting_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    pass1_tasks = build_pass1_tasks(params)
    pass1_results = run_tasks(pass1_tasks, active_runner, timeout)
    pass1_compiled = compile_agent_outputs("Pass 1 Deal Discovery", pass1_tasks, pass1_results)
    (supporting_dir / "pass1_compiled_deals.md").write_text(pass1_compiled, encoding="utf-8")

    candidates = candidates_from_results(pass1_results)
    deduped = dedupe_deals(candidates)
    qualified = filter_qualified_deals(deduped, params.min_multiples)

    if db_path is not None:
        conn = _db.open_db(db_path)
        run_id = _db.new_run_id()
        _db.insert_run(conn, run_id, params)
        _db.insert_deals(conn, run_id, deduped, qualified_keys={d.key() for d in qualified})
        conn.close()

    qualified_payload = [deal.model_dump(mode="json") for deal in qualified]
    qualified_path = supporting_dir / "qualified_deals.json"
    write_json(qualified_path, qualified_payload)

    pass2_tasks = build_pass2_tasks(params, qualified)
    pass2_results = run_tasks(pass2_tasks, active_runner, timeout)
    pass2_compiled = compile_agent_outputs("Pass 2 Deal Deep Dives", pass2_tasks, pass2_results)
    (supporting_dir / "pass2_compiled_deep.md").write_text(pass2_compiled, encoding="utf-8")

    qc_prompt = build_qc_prompt(params, pass2_compiled)
    qc_result = normalize_result(active_runner(qc_prompt, timeout))
    qc_report_path = supporting_dir / "qc_report.md"
    qc_report_path.write_text(qc_result.output, encoding="utf-8")
    final_markdown = output_dir / "final_deliverable.md"
    final_markdown.write_text(qc_result.output, encoding="utf-8")

    metadata = {
        "params": params.model_dump(mode="json"),
        "pass1": {key: value.model_dump(mode="json") for key, value in pass1_results.items()},
        "pass2": {key: value.model_dump(mode="json") for key, value in pass2_results.items()},
        "qc": qc_result.model_dump(mode="json"),
    }
    write_json(metadata_dir / "run_metadata.json", metadata)
    return PipelinePaths(
        output_dir=output_dir,
        final_markdown=final_markdown,
        final_pdf=output_dir / "final_deliverable.pdf",
        comps_excel=output_dir / "precedent_comps.xlsx",
        qualified_deals=qualified_path,
    )
