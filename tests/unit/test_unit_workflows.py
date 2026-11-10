"""Eight isolated service-layer unit tests from the final test plan."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.approval import (
    ApprovalDecisionValidationError,
    ApprovalService,
)
from app.services.degree_progress import DegreeProgressService
from app.services.semester_plan import (
    SemesterPlanNotEditableError,
    SemesterPlanService,
)

# WORKFLOW 1
@pytest.fixture
def degree_service():
    """Mock all database calls while exercising the real service logic."""
    repository = MagicMock()
    repository.get_student_by_user_id.return_value = SimpleNamespace(
        id=10, degree_plan_id=20,
    )
    repository.get_degree_plan.return_value = SimpleNamespace(
        id=20, programme_id=30, start_year=2024,
    )
    repository.get_programme_course_mappings.return_value = [
        SimpleNamespace(course_id=40)
    ]
    repository.get_completions_with_courses.return_value = []
    repository.create_course_completion.return_value = SimpleNamespace(
        grade="A", academic_year=2025, semester_number=1,
    )
    return DegreeProgressService(repository), repository

# UT 1
def test_valid_course_completion(degree_service):
    service, repo = degree_service
    completion = service.add_course_completion(
        user_id=1, course_id=40, grade="A", academic_year=2025,
        semester_number=1,
    )

    assert completion.grade == "A"
    assert completion.academic_year == 2025
    assert completion.semester_number == 1
    repo.create_course_completion.assert_called_once_with(
        student_id=10, course_id=40, grade="A",
        academic_year=2025, semester_number=1,
    )

# UT 2
def test_duplicate_course_completion(degree_service):
    service, repo = degree_service
    repo.get_completions_with_courses.return_value = [
        (SimpleNamespace(grade="B"), SimpleNamespace(id=40))
    ]

    with pytest.raises(ValueError, match="already marked as completed"):
        service.add_course_completion(
            user_id=1, course_id=40, grade="A", academic_year=2025,
            semester_number=1,
        )
    repo.create_course_completion.assert_not_called()

# UT 3
def test_invalid_course_grade(degree_service):
    service, repo = degree_service

    with pytest.raises(ValueError, match="Choose a grade"):
        service.add_course_completion(
            user_id=1, course_id=40, grade="Z", academic_year=2025,
            semester_number=1,
        )
    repo.create_course_completion.assert_not_called()

# UT 4
def test_course_outside_programme(degree_service):
    service, repo = degree_service

    with pytest.raises(ValueError, match="in your degree programme"):
        service.add_course_completion(
            user_id=1, course_id=999, grade="A", academic_year=2025,
            semester_number=1,
        )
    repo.create_course_completion.assert_not_called()

# WORKFLOW 2
@pytest.fixture
def semester_service():
    repo = MagicMock()
    student = SimpleNamespace(id=10)
    plan = SimpleNamespace(id=50, student_id=10, status="draft")
    repo.get_student_by_user_id.return_value = student
    repo.get_plan_for_student.return_value = plan
    return SemesterPlanService(repo), repo, plan

# UT 5
def test_valid_semester_plan_submission(semester_service):
    service, repo, plan = semester_service
    repo.get_selected_offerings.return_value = [object()]  # at least one course

    def save_submission(existing_plan):
        existing_plan.status = "under_review"
        return existing_plan

    repo.submit_plan.side_effect = save_submission
    result = service.submit_for_review(user_id=1, plan_id=50)

    assert result.status == "under_review"
    repo.submit_plan.assert_called_once_with(plan)

# UT 6
def test_empty_semester_plan_submission(semester_service):
    service, repo, _ = semester_service
    repo.get_selected_offerings.return_value = []

    with pytest.raises(SemesterPlanNotEditableError, match="Add at least one course"):
        service.submit_for_review(user_id=1, plan_id=50)
    repo.submit_plan.assert_not_called()


# WORKFLOW 3

# UT 7
def test_valid_approval_decision():
    repo = MagicMock()
    advisor = SimpleNamespace(id=70)
    approval = SimpleNamespace(id=80, status="pending")
    plan = SimpleNamespace(id=50, status="under_review")
    repo.get_advisor_by_user_id.return_value = advisor
    repo.get_request_for_review.return_value = (
        approval, plan, None, None, None,
    )

    ApprovalService(repo).review_plan(
        user_id=2, request_id=80, outcome="approved", comments="Approved",
    )

    repo.review_request.assert_called_once_with(
        approval, plan, 70, "approved", "Approved"
    )

# UT 8
def test_invalid_approval_decision():
    repo = MagicMock()

    with pytest.raises(ApprovalDecisionValidationError, match="valid review decision"):
        ApprovalService(repo).review_plan(
            user_id=2, request_id=80, outcome="pending", comments="",
        )
    repo.review_request.assert_not_called()