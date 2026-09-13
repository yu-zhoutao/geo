from __future__ import annotations

from argparse import ArgumentParser
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

from app.evaluation.aggregation import aggregate_campaign
from app.evaluation.benchmarks import BenchmarkScenario, load_benchmark_scenario
from app.evaluation.llm_judge import (
    DeepSeekJudgeProvider,
    GLMJudgeProvider,
    JUDGE_INPUT_FILENAME,
    JUDGE_SCORE_FILENAME,
    JudgeConfig,
    JudgeProvider,
    write_judge_score,
)
from app.evaluation.run_bundles import RUN_MANIFEST_FILENAME


LEGACY_DETERMINISTIC_SCORE_FILENAME = 'deterministic-score.json'


@dataclass(frozen=True, slots=True)
class CampaignScoringResult:
    campaign_root: Path
    judge_score_paths: tuple[Path, ...]
    aggregate_summary: dict[str, object]


async def score_campaign_run(
    campaign_root: Path,
    *,
    judge_provider: JudgeProvider | None = None,
    judge_config: JudgeConfig | None = None,
    overwrite_scores: bool = False,
    judge_concurrency: int = 1,
) -> CampaignScoringResult:
    if judge_concurrency <= 0:
        raise ValueError('judge_concurrency must be positive')
    judge_paths: list[Path] = []
    run_manifest_paths: list[Path] = sorted((campaign_root / 'runs').glob('**/' + RUN_MANIFEST_FILENAME))
    for run_manifest_path in run_manifest_paths:
        if overwrite_scores:
            bundle_path: Path = run_manifest_path.parent
            _clear_existing_scores(bundle_path, include_judge=judge_provider is not None and judge_config is not None)
    if judge_provider is not None and judge_config is not None:
        judge_paths.extend(
            await _write_missing_judge_scores(
                run_manifest_paths,
                judge_provider=judge_provider,
                judge_config=judge_config,
                judge_concurrency=judge_concurrency,
            )
        )
    aggregate_summary: dict[str, object] = aggregate_campaign(campaign_root)
    return CampaignScoringResult(
        campaign_root=campaign_root,
        judge_score_paths=tuple(judge_paths),
        aggregate_summary=aggregate_summary,
    )


def _scenario_from_run_manifest(path: Path) -> BenchmarkScenario:
    payload = json.loads(path.read_text(encoding='utf-8'))
    scenario = payload.get('scenario') if isinstance(payload, dict) else None
    fixture_path = scenario.get('fixture_path') if isinstance(scenario, dict) else None
    scenario_id = scenario.get('id') if isinstance(scenario, dict) else None
    if not isinstance(fixture_path, str) or not fixture_path:
        raise ValueError(f'Run manifest does not include a scenario fixture path: {path}')
    local_path: Path = _local_fixture_path(Path(fixture_path))
    if local_path.exists():
        return load_benchmark_scenario(local_path)
    if isinstance(scenario_id, str) and scenario_id:
        return _scenario_by_id(scenario_id, path)
    return load_benchmark_scenario(local_path)


async def _write_missing_judge_scores(
    run_manifest_paths: list[Path],
    *,
    judge_provider: JudgeProvider,
    judge_config: JudgeConfig,
    judge_concurrency: int,
) -> tuple[Path, ...]:
    semaphore = asyncio.Semaphore(judge_concurrency)

    async def write_one(run_manifest_path: Path) -> Path | None:
        bundle_path: Path = run_manifest_path.parent
        if (bundle_path / JUDGE_SCORE_FILENAME).exists():
            return None
        async with semaphore:
            scenario: BenchmarkScenario = _scenario_from_run_manifest(run_manifest_path)
            return await write_judge_score(scenario, bundle_path, judge_provider, judge_config)

    results: list[Path | None] = await asyncio.gather(
        *(write_one(run_manifest_path) for run_manifest_path in run_manifest_paths)
    )
    return tuple(path for path in results if path is not None)


def _local_fixture_path(path: Path) -> Path:
    if path.exists():
        return path
    parts: tuple[str, ...] = path.parts
    try:
        index = parts.index('app')
    except ValueError:
        return path
    candidate: Path = Path(*parts[index:])
    if candidate.exists():
        return candidate
    return path


def _scenario_by_id(scenario_id: str, manifest_path: Path) -> BenchmarkScenario:
    from app.evaluation.benchmarks import validate_benchmark_suite

    for scenario in validate_benchmark_suite(Path('app/agent_assets/benchmarks')):
        if scenario.id == scenario_id:
            return scenario
    raise ValueError(f'Run manifest scenario id does not match local benchmark suite: {manifest_path}')


def _clear_existing_scores(bundle_path: Path, *, include_judge: bool) -> None:
    paths: list[Path] = [bundle_path / LEGACY_DETERMINISTIC_SCORE_FILENAME]
    if include_judge:
        paths.extend(
            [
                bundle_path / JUDGE_INPUT_FILENAME,
                bundle_path / JUDGE_SCORE_FILENAME,
            ]
        )
        paths.extend(sorted(bundle_path.glob('judge-response-*.txt')))
    for path in paths:
        if path.exists():
            path.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = ArgumentParser(description='Score an executed geospatial evaluation campaign.')
    parser.add_argument('campaign_root', type=Path, help='Executed campaign output root.')
    parser.add_argument('--judge-provider', choices=('glm', 'deepseek'), default='glm')
    parser.add_argument('--judge-model', default=None, help='Run LLM judge scoring with this model.')
    parser.add_argument('--judge-temperature', type=float, default=0.0)
    parser.add_argument('--judge-max-retries', type=int, default=1)
    parser.add_argument('--judge-concurrency', type=int, default=1)
    parser.add_argument('--overwrite-scores', action='store_true', help='Replace existing judge score files.')
    args = parser.parse_args(argv)

    if args.judge_model:
        judge_provider: JudgeProvider
        if args.judge_provider == 'deepseek':
            judge_provider = DeepSeekJudgeProvider()
        else:
            judge_provider = GLMJudgeProvider()
        result = asyncio.run(
            score_campaign_run(
                args.campaign_root,
                judge_provider=judge_provider,
                judge_config=JudgeConfig(
                    model=args.judge_model,
                    temperature=args.judge_temperature,
                    max_retries=args.judge_max_retries,
                ),
                overwrite_scores=args.overwrite_scores,
                judge_concurrency=args.judge_concurrency,
            )
        )
    else:
        result = asyncio.run(
            score_campaign_run(
                args.campaign_root,
                overwrite_scores=args.overwrite_scores,
                judge_concurrency=args.judge_concurrency,
            )
        )
    print(
        json.dumps(
            {
                'campaign_root': str(result.campaign_root),
                'judge_score_count': len(result.judge_score_paths),
                'run_count': result.aggregate_summary['run_count'],
                'scored_run_count': result.aggregate_summary['scored_run_count'],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
