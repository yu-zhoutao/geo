from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.benchmarks import BenchmarkValidationError


JUDGE_RUBRIC_SCHEMA = 'geo-agent.evaluation.judge-rubric.v1'
GEOSPATIAL_AGENT_RUBRIC_ID = 'geospatial-task-quality-v2'
LEGACY_GEOSPATIAL_AGENT_RUBRIC_ID = 'geospatial-agent-v1'


@dataclass(frozen=True, slots=True)
class JudgeDimension:
    id: str
    label: str
    description: str

    def as_json(self) -> dict[str, object]:
        return {
            'id': self.id,
            'label': self.label,
            'description': self.description,
            'score_range': {'min': 1, 'max': 5},
        }


@dataclass(frozen=True, slots=True)
class JudgeRubric:
    id: str
    dimensions: tuple[JudgeDimension, ...]

    def as_json(self) -> dict[str, object]:
        return {
            'schema': JUDGE_RUBRIC_SCHEMA,
            'id': self.id,
            'dimensions': [dimension.as_json() for dimension in self.dimensions],
        }


GEOSPATIAL_AGENT_RUBRIC = JudgeRubric(
    id=GEOSPATIAL_AGENT_RUBRIC_ID,
    dimensions=(
        JudgeDimension(
            id='method_selection',
            label='Method selection',
            description=(
                'Scores whether the chosen geospatial method matches the user task, geometry type, data support, '
                'and data limitations. Give 5 only when the method is correct and explicitly distinguishes nearby '
                'alternatives such as KDE, IDW, and Getis-Ord Gi*. Give at most 3 when the method is plausible but '
                'under-justified, at most 2 for a method-family mismatch, and at most 2 when the run forces an '
                'analysis that the data cannot support.'
            ),
        ),
        JudgeDimension(
            id='data_readiness',
            label='Data readiness',
            description=(
                'Scores whether the run inspects task-critical inputs such as geometry type, value fields, missing values, '
                'study area, spatial support, sample size, and overlap. Give 5 only when the run checks the prerequisites '
                'needed for the requested analysis. Give at most 3 when important assumptions are left implicit.'
            ),
        ),
        JudgeDimension(
            id='crs_and_units',
            label='CRS and units',
            description=(
                'Scores whether CRS, projection, distance, area, bandwidth, raster cell size, and area-of-use constraints '
                'are handled correctly. Give 5 only when metric operations use a defensible projected CRS or equivalent '
                'geodesic method and units are stated accurately. Give 1-2 for degree-meter confusion or unsafe CRS use.'
            ),
        ),
        JudgeDimension(
            id='parameterization',
            label='Parameterization',
            description=(
                'Scores whether bandwidths, search radii, cell sizes, interpolation powers, neighbor rules, weights, '
                'significance thresholds, or stopping criteria are appropriate for the task and data. Give 5 only when '
                'parameters are justified and checked against task scale; give at most 4 when the run states parameters '
                'but does not test sensitivity where it matters.'
            ),
        ),
        JudgeDimension(
            id='execution_correctness',
            label='Execution correctness',
            description=(
                'Scores whether the actual analysis workflow is computationally coherent and produces outputs matching '
                'the requested task. Give 5 only when preprocessing, analysis, clipping/masking, validation, and generated '
                'outputs or code are internally consistent. Penalize unresolved tool errors, placeholder results, or outputs '
                'that do not match the claimed computation, but do not require a framework to emit this project\'s app-specific '
                'artifact schema.'
            ),
        ),
        JudgeDimension(
            id='uncertainty_and_sensitivity',
            label='Uncertainty and sensitivity',
            description=(
                'Scores whether the run evaluates uncertainty, sensitivity, sample-size limits, edge effects, validation '
                'error, or robustness when those issues affect the task. Give 5 only when meaningful checks are actually '
                'performed or when the run explicitly avoids unsupported analysis because of geospatial data limitations; '
                'merely listing limitations without checking them should normally score no higher than 4.'
            ),
        ),
        JudgeDimension(
            id='claim_validity',
            label='Claim validity',
            description=(
                'Scores whether final claims stay within what the method and data support. Give 5 only when descriptive, '
                'predictive, and inferential claims are clearly separated. Give 1-2 for unsupported significance, causality, '
                'risk, or policy claims.'
            ),
        ),
    ),
)


def get_judge_rubric(rubric_id: str) -> JudgeRubric:
    if rubric_id in {GEOSPATIAL_AGENT_RUBRIC_ID, LEGACY_GEOSPATIAL_AGENT_RUBRIC_ID}:
        return GEOSPATIAL_AGENT_RUBRIC
    raise BenchmarkValidationError(f'Unknown judge rubric: {rubric_id}')
