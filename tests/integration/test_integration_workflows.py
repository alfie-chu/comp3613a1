"""Five integration tests using real repositories, a test DB, and FastAPI."""

from datetime import date

import jwt
from fastapi.testclient import TestClient
from sqlmodel import select

from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models.approval import ApprovalRequest
from app.models.degree_progress import CourseCompletion
from app.models.semester_plan import SemesterPlan
from app.repositories.approval import ApprovalRepository
from app.repositories.degree_progress import DegreeProgressRepository
from app.repositories.semester_plan import SemesterPlanRepository
from app.services.approval import ApprovalService
from app.services.degree_progress import DegreeProgressService
from app.services.semester_plan import SemesterPlanService


def _completed_course(db, sample_data):
    service = DegreeProgressService(DegreeProgressRepository(db))
    return service.add_course_completion(
        user_id=sample_data["student_user"].id,
        course_id=sample_data["course_1"].id,
        grade="A",
        academic_year=date.today().year - 1,
        semester_number=1,
    )


def _submitted_plan(db, sample_data):
    """Carry out the real create -> add course -> submit workflow."""
    service = SemesterPlanService(SemesterPlanRepository(db))
    user_id = sample_data["student_user"].id
    plan = service.start_plan(
        user_id=user_id, semester_id=sample_data["semester"].id,
    )
    service.add_course(
        user_id=user_id, plan_id=plan.id,
        offering_id=sample_data["offering"].id,
    )
    return service.submit_for_review(user_id=user_id, plan_id=plan.id)

# Test 1
def test_add_course_completion(db, sample_data):
    completion = _completed_course(db, sample_data)
    saved = db.exec(
        select(CourseCompletion).where(CourseCompletion.id == completion.id)
    ).one()
    assert saved.grade == "A"
    assert saved.academic_year == date.today().year - 1
    assert saved.semester_number == 1

    rows = DegreeProgressRepository(db).get_completions_with_courses(
        sample_data["student"].id
    )
    assert len(rows) == 1
    assert rows[0][1].course_code == "COMP1001"

# Test 2
def test_get_degree_progress(db, sample_data):
    _completed_course(db, sample_data)
    progress = DegreeProgressService(
        DegreeProgressRepository(db)
    ).get_progress_for_student(sample_data["student_user"].id)

    assert progress.completed_credits == 3
    assert progress.total_credits_required == 12
    assert progress.progress_percent == 25
    assert [c.course_code for c in progress.completed_courses] == ["COMP1001"]
    assert "COMP1002" in [
        r.course_code for r in progress.outstanding_requirements
    ]

# Test 3
def test_create_and_submit_semester_plan(db, sample_data):
    plan = _submitted_plan(db, sample_data)
    saved_plan = db.get(SemesterPlan, plan.id)
    assert saved_plan.status == "under_review"
    assert saved_plan.submitted_at is not None

    selections = SemesterPlanRepository(db).get_selected_offerings(plan.id)
    assert len(selections) == 1
    assert selections[0][2].course_code == "COMP1001"

    request = db.exec(
        select(ApprovalRequest).where(ApprovalRequest.semester_plan_id == plan.id)
    ).one()
    assert request.status == "pending"

# Test 4
def test_approve_semester_plan(db, sample_data):
    plan = _submitted_plan(db, sample_data)
    request = db.exec(
        select(ApprovalRequest).where(ApprovalRequest.semester_plan_id == plan.id)
    ).one()
    ApprovalService(ApprovalRepository(db)).review_plan(
        user_id=sample_data["admin_user"].id,
        request_id=request.id,
        outcome="approved",
        comments="Course choices approved",
    )

    db.refresh(request)
    db.refresh(plan)
    assert request.status == "approved"
    assert request.advisor_comments == "Course choices approved"
    assert request.advisor_id is not None
    assert request.reviewed_at is not None
    assert plan.status == "approved"

# Test 5
def test_unauthorized_admin_access(db, sample_data):
    """Real JWT authentication + FastAPI admin-role guard (no mocked auth)."""
    def test_session_override():
        yield db

    app.dependency_overrides[get_session] = test_session_override
    try:
        # Without any login cookie, the protected route must be denied.
        # Do not enter lifespan here: it would initialize the app's default
        # engine. Only the fixture-provided test database should be used.
        client = TestClient(app)
        try:
            no_cookie = client.get("/admin/review-plans", follow_redirects=False)
            assert no_cookie.status_code == 401

            # Valid student token should authenticate but fail the role check.
            token = jwt.encode(
                {"sub": str(sample_data["student_user"].id)},
                get_settings().secret_key,
                algorithm=get_settings().jwt_algorithm,
            )
            client.cookies.set("access_token", token)
            denied = client.get("/admin/review-plans", follow_redirects=False)
            assert denied.status_code == 401  # Current MyAdvisor code uses 401.
        finally:
            client.close()
    finally:
        app.dependency_overrides.clear()