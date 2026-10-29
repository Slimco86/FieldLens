"""Deterministic analytic trajectory, reference validation and proximity engine."""

from fieldlens.engineering.trajectory.mincurve import (
    Trajectory,
    compute_trajectory,
    display_samples,
)
from fieldlens.engineering.trajectory.proximity import (
    PROXIMITY_CAVEAT,
    ProximityResult,
    ProximityStatus,
    closest_approach,
)
from fieldlens.engineering.trajectory.survey import (
    NorthReference,
    Survey,
    SurveyBlockedError,
    SurveyIssue,
    SurveyIssueCode,
    SurveyReference,
    SurveyStation,
    validate_survey,
)

__all__ = [
    "PROXIMITY_CAVEAT",
    "NorthReference",
    "ProximityResult",
    "ProximityStatus",
    "Survey",
    "SurveyBlockedError",
    "SurveyIssue",
    "SurveyIssueCode",
    "SurveyReference",
    "SurveyStation",
    "Trajectory",
    "closest_approach",
    "compute_trajectory",
    "display_samples",
    "validate_survey",
]
