"""Shared fixtures for the MyAdvisor Assignment 2 test suite.

All integration tests use an isolated in-memory SQLite database, never the
application's regular database. Run pytest from the repository root.
"""

import os
from datetime import date

# Set before any `app.*` imports; app.database constructs its default engine
# during import. This ensures a test run never points at production by default.
os.environ["DATABASE_URI"] = "sqlite:///./myadvisor_test_import.db"
os.environ["ENV"] = "testing"
os.environ["SECRET_KEY"] = "myadvisor-only-for-local-pytest-tests"

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

import app.models  # noqa: F401 -- register all tables on SQLModel.metadata
from app.models.approval import Advisor
from app.models.degree_progress import (
    Course,
    ProgrammeCatalogue,
    ProgrammeCourseMapping,
    Semester,
)
from app.models.semester_plan import CourseOffering
from app.models.user import User
from app.repositories.degree_progress import DegreeProgressRepository
from app.services.degree_progress import DegreeProgressService


@pytest.fixture
def db():
    """Fresh, isolated database for each integration test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def sample_data(db):
    """Users, programme, two courses, an offering, and a real student profile."""
    student_user = User(
        username="test_student", email="student@example.com",
        password="not-a-real-password-hash", role="student",
    )
    admin_user = User(
        username="test_admin", email="admin@example.com",
        password="not-a-real-password-hash", role="admin",
    )
    programme = ProgrammeCatalogue(
        programme_name="BSc Computer Science",
        total_credits_required=12,
        standard_duration_years=3,
        status="active",
    )
    course_1 = Course(
        course_code="COMP1001", title="Programming I", credits=3,
        category="Core", level="1000",
    )
    course_2 = Course(
        course_code="COMP1002", title="Programming II", credits=3,
        category="Core", level="1000",
    )
    future_year = date.today().year + 1
    semester = Semester(
        semester_name=f"Semester 1 {future_year}/{future_year + 1}",
        year=future_year,
        start_date=date(future_year, 8, 17),
        end_date=date(future_year, 12, 18),
    )

    db.add_all([student_user, admin_user, programme, course_1, course_2, semester])
    db.commit()
    for row in (student_user, admin_user, programme, course_1, course_2, semester):
        db.refresh(row)

    db.add_all([
        ProgrammeCourseMapping(
            programme_id=programme.id, course_id=course_1.id,
            requirement_type="Core", is_required=True, completion_rule="pass",
        ),
        ProgrammeCourseMapping(
            programme_id=programme.id, course_id=course_2.id,
            requirement_type="Core", is_required=True, completion_rule="pass",
        ),
        Advisor(
            user_id=admin_user.id, first_name="Test", last_name="Advisor",
            email=admin_user.email, department="Computing",
        ),
        CourseOffering(
            course_id=course_1.id, semester_id=semester.id,
            section="A", delivery_mode="online", status="open",
        ),
    ])
    db.commit()

    profile_service = DegreeProgressService(DegreeProgressRepository(db))
    student = profile_service.setup_student_profile(
        user_id=student_user.id,
        email=student_user.email,
        student_number="123456789",
        first_name="Test",
        last_name="Student",
        programme_id=programme.id,
        start_year=date.today().year - 1,
    )

    from sqlmodel import select
    from app.models.semester_plan import CourseOffering as OfferingModel
    offering = db.exec(
        select(OfferingModel).where(OfferingModel.course_id == course_1.id)
    ).one()

    return {
        "student_user": student_user,
        "admin_user": admin_user,
        "student": student,
        "programme": programme,
        "course_1": course_1,
        "course_2": course_2,
        "semester": semester,
        "offering": offering,
    }