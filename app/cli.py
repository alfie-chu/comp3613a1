#!/usr/bin/env python3
"""FastStarter project CLI — stdlib argparse (no extra CLI library).

From the project root (venv active, deps installed; ``.env`` optional — falls back to ``.env.example``):

    python manage.py init
    python manage.py run
    python manage.py users
    python manage.py report --name "Student Name" --id "816000000"
    python manage.py usecase
    python manage.py skills-verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_models_loaded() -> None:
    import app.models  # noqa: F401


def cmd_init(args: argparse.Namespace) -> None:
    """Create database tables (drops existing by default) and seed demo data."""
    from app.config import get_settings
    from app.database import drop_all, ensure_db_and_tables

    _ensure_models_loaded()
    if args.drop:
        print("Dropping all tables…")
        # Drop can fail on a brand-new empty DB; create path still retries.
        try:
            drop_all()
        except Exception as exc:  # noqa: BLE001
            from app.database import is_db_not_ready_error

            if not is_db_not_ready_error(exc):
                raise
            print(f"Database not ready yet while dropping ({exc}); continuing…")
    print("Creating tables…")
    ensure_db_and_tables()
    print(f"Database ready ({get_settings().database_uri}).")
    if getattr(args, "seed", True):
        cmd_seed(args)


def cmd_seed(args: argparse.Namespace) -> None:
    """Insert demo users and a sample student degree-progress record.

    bob / bobpass       (regular_user)
    admin / adminpass   (admin)
    """
    from datetime import date, datetime

    from app.database import ensure_db_and_tables, get_cli_session
    from app.models.degree_progress import (
        Course,
        CourseCompletion,
        CoursePrerequisite,
        DegreePlan,
        DegreeRequirement,
        Semester,
    )
    from app.models.approval import Advisor
    from app.models.semester_plan import CourseOffering, CourseSelection, SemesterPlan
    from app.models.student import Student
    from app.repositories.user import UserRepository
    from app.schemas.user import AdminCreate, RegularUserCreate
    from app.utilities.security import encrypt_password
    from sqlmodel import select

    _ensure_models_loaded()
    ensure_db_and_tables()

    demo_users = [
        ("bob", "bob@example.com", "bobpass", "regular_user"),
        ("admin", "admin@example.com", "adminpass", "admin"),
    ]

    created = 0
    skipped = 0
    with get_cli_session() as session:
        repo = UserRepository(session)
        for username, email, password, role in demo_users:
            if repo.get_by_username(username):
                print(f"  skip  {username} (already exists)")
                skipped += 1
                continue
            payload_cls = AdminCreate if role == "admin" else RegularUserCreate
            repo.create(
                payload_cls(
                    username=username,
                    email=email,
                    password=encrypt_password(password),
                    role=role,
                )
            )
            print(f"  create {username} ({role})")
            created += 1

        bob = repo.get_by_username("bob")
        if bob is None or bob.id is None:
            raise RuntimeError("Unable to seed the MyAdvisor student demo account.")
        admin = repo.get_by_username("admin")
        if admin is None or admin.id is None:
            raise RuntimeError("Unable to seed the MyAdvisor administrator account.")

        advisor = session.exec(
            select(Advisor).where(Advisor.user_id == admin.id)
        ).one_or_none()
        if advisor is None:
            session.add(
                Advisor(
                    user_id=admin.id,
                    first_name="Admin",
                    last_name="Advisor",
                    email="admin@example.com",
                    department="Academic Advising",
                )
            )
            session.commit()
            print("  create advisor profile for admin")

        existing_student = session.exec(
            select(Student).where(Student.user_id == bob.id)
        ).one_or_none()
        student = existing_student
        degree_plan = (
            session.get(DegreePlan, student.degree_plan_id)
            if student is not None
            else None
        )
        if student is None:
            degree_plan = DegreePlan(
                programme_name="BSc Computer Science",
                total_credits_required=93,
                start_year=2026,
                end_year=2029,
                status="active",
            )
            session.add(degree_plan)
            session.flush()
            if degree_plan.id is None:
                raise RuntimeError("Unable to create Bob's degree plan.")

            student = Student(
                user_id=bob.id,
                student_number="100000001",
                first_name="Bob",
                last_name="Student",
                email="bob@example.com",
                degree_plan_id=degree_plan.id,
                status="active",
            )
            session.add(student)
            session.flush()
            if student.id is None:
                raise RuntimeError("Unable to create Bob's student profile.")
            print("  create sample student profile for bob")
        elif degree_plan is None:
            raise RuntimeError("Bob's student profile references a missing degree plan.")

        if student.id is None or degree_plan.id is None:
            raise RuntimeError("Bob's student profile and degree plan must be saved.")

        course_data = [
            ("COMP 1001", "Introduction to Computing", 3, "Core", "1000"),
            ("COMP 1602", "Programming Fundamentals", 3, "Core", "1000"),
            ("MATH 1140", "Discrete Mathematics", 3, "Mathematics", "1000"),
            ("COMP 1710", "Computer Systems", 3, "Core", "1000"),
            ("MATH 1210", "Calculus for Computing", 3, "Mathematics", "1000"),
            ("STAT 2001", "Statistics for Computing", 3, "Mathematics", "2000"),
            ("COMP 2610", "Data Structures", 3, "Core", "2000"),
            ("COMP 2620", "Database Systems", 3, "Core", "2000"),
            ("COMP 2630", "Computer Networks", 3, "Core", "2000"),
            ("COMP 2640", "Web Application Development", 3, "Core", "2000"),
            ("COMP 2650", "Human-Computer Interaction", 3, "Elective", "2000"),
            ("COMP 3010", "Software Engineering", 3, "Core", "3000"),
            ("COMP 3005", "Operating Systems", 3, "Core", "3000"),
            (
                "COMP 3015",
                "Introduction to Artificial Intelligence",
                3,
                "Elective",
                "3000",
            ),
            ("COMP 3020", "Cybersecurity Fundamentals", 3, "Elective", "3000"),
            ("COMP 3030", "Mobile Application Development", 3, "Elective", "3000"),
            ("COMP 3040", "Data Analytics", 3, "Elective", "3000"),
        ]
        courses_by_code: dict[str, Course] = {}
        for course_code, title, credits, category, level in course_data:
            course = session.exec(
                select(Course).where(Course.course_code == course_code)
            ).one_or_none()
            if course is None:
                course = Course(
                    course_code=course_code,
                    title=title,
                    credits=credits,
                    category=category,
                    level=level,
                )
                session.add(course)
            courses_by_code[course_code] = course
        session.flush()
        if any(course.id is None for course in courses_by_code.values()):
            raise RuntimeError("Unable to save the sample course catalogue.")

        history_semester = session.exec(
            select(Semester).where(
                Semester.semester_name == "Semester 2 2025/2026",
                Semester.year == 2025,
            )
        ).one_or_none()
        if history_semester is None:
            history_semester = Semester(
                semester_name="Semester 2 2025/2026",
                year=2025,
                start_date=date(2026, 1, 12),
                end_date=date(2026, 5, 1),
            )
            session.add(history_semester)
            session.flush()
        if history_semester.id is None:
            raise RuntimeError("Unable to save the sample history semester.")

        for course_code in ("COMP 1001", "COMP 1602", "MATH 1140"):
            course = courses_by_code[course_code]
            completion = session.exec(
                select(CourseCompletion).where(
                    CourseCompletion.student_id == student.id,
                    CourseCompletion.course_id == course.id,
                )
            ).one_or_none()
            if completion is None:
                session.add(
                    CourseCompletion(
                        student_id=student.id,
                        course_id=course.id,
                        semester_id=history_semester.id,
                        grade="B+",
                        completed_at=datetime(2026, 5, 15),
                        is_transfer=False,
                    )
                )

        requirement_data = (
            ("COMP 2610", "Core"),
            ("COMP 3010", "Core"),
            ("COMP 2620", "Core"),
            ("COMP 2630", "Core"),
            ("COMP 3005", "Core"),
        )
        for course_code, requirement_type in requirement_data:
            course = courses_by_code[course_code]
            requirement = session.exec(
                select(DegreeRequirement).where(
                    DegreeRequirement.degree_plan_id == degree_plan.id,
                    DegreeRequirement.course_id == course.id,
                )
            ).one_or_none()
            if requirement is None:
                session.add(
                    DegreeRequirement(
                        degree_plan_id=degree_plan.id,
                        course_id=course.id,
                        requirement_type=requirement_type,
                        is_required=True,
                        completion_rule="Complete the course",
                    )
                )

        current_semester = session.exec(
            select(Semester).where(
                Semester.semester_name == "Semester 1 2026/2027",
                Semester.year == 2026,
            )
        ).one_or_none()
        if current_semester is None:
            current_semester = Semester(
                semester_name="Semester 1 2026/2027",
                year=2026,
                start_date=date(2026, 8, 17),
                end_date=date(2026, 12, 18),
            )
            session.add(current_semester)
            session.flush()
        if current_semester.id is None:
            raise RuntimeError("Unable to save the sample current semester.")

        offerings_by_code: dict[str, CourseOffering] = {}
        for course_code in courses_by_code:
            course = courses_by_code[course_code]
            offering = session.exec(
                select(CourseOffering).where(
                    CourseOffering.course_id == course.id,
                    CourseOffering.semester_id == current_semester.id,
                    CourseOffering.section == "01",
                )
            ).one_or_none()
            if offering is None:
                offering = CourseOffering(
                    course_id=course.id,
                    semester_id=current_semester.id,
                    section="01",
                    delivery_mode="In person",
                    status="open",
                )
                session.add(offering)
            offerings_by_code[course_code] = offering
        session.flush()
        if any(offering.id is None for offering in offerings_by_code.values()):
            raise RuntimeError("Unable to save the sample course offerings.")

        prerequisite_pairs = (
            ("COMP 2610", "COMP 1602"),
            ("COMP 3010", "COMP 2610"),
            ("COMP 2620", "COMP 1602"),
            ("COMP 2630", "COMP 1602"),
            ("COMP 2640", "COMP 1602"),
            ("COMP 3005", "COMP 2610"),
            ("COMP 3015", "COMP 2610"),
            ("COMP 3020", "COMP 2610"),
            ("COMP 3030", "COMP 2640"),
            ("COMP 3040", "STAT 2001"),
            ("STAT 2001", "MATH 1140"),
        )
        for course_code, prerequisite_code in prerequisite_pairs:
            course = courses_by_code[course_code]
            prerequisite = courses_by_code[prerequisite_code]
            relationship = session.exec(
                select(CoursePrerequisite).where(
                    CoursePrerequisite.course_id == course.id,
                    CoursePrerequisite.prerequisite_course_id == prerequisite.id,
                )
            ).one_or_none()
            if relationship is None:
                session.add(
                    CoursePrerequisite(
                        course_id=course.id,
                        prerequisite_course_id=prerequisite.id,
                    )
                )

        semester_plan = session.exec(
            select(SemesterPlan)
            .where(
                SemesterPlan.student_id == student.id,
                SemesterPlan.semester_id == current_semester.id,
                SemesterPlan.status.in_(("draft", "revision_required")),
            )
            .order_by(SemesterPlan.created_at.desc())
        ).first()
        if semester_plan is None:
            semester_plan = SemesterPlan(
                student_id=student.id,
                semester_id=current_semester.id,
                status="draft",
            )
            session.add(semester_plan)
            session.flush()
        if semester_plan.id is None:
            raise RuntimeError("Unable to save Bob's sample semester plan.")

        for course_code in ("COMP 2610", "COMP 3010"):
            offering = offerings_by_code[course_code]
            selection = session.exec(
                select(CourseSelection).where(
                    CourseSelection.semester_plan_id == semester_plan.id,
                    CourseSelection.course_offering_id == offering.id,
                )
            ).one_or_none()
            if selection is None:
                session.add(
                    CourseSelection(
                        semester_plan_id=semester_plan.id,
                        course_offering_id=offering.id,
                    )
                )

        session.commit()
        print("  ensure sample degree progress and draft plan for bob")

    print(f"Seed done — created {created}, skipped {skipped}.")
    print("Login with bob/bobpass or admin/adminpass")


def cmd_run(args: argparse.Namespace) -> None:
    """Start the FastAPI app with Uvicorn."""
    import uvicorn

    from app.config import get_settings

    settings = get_settings()
    bind_host = args.host or settings.app_host
    bind_port = args.port or settings.app_port
    if args.reload is None:
        use_reload = settings.env.lower() != "production"
    else:
        use_reload = args.reload
    print(f"Starting FastStarter on http://{bind_host}:{bind_port} (reload={use_reload})")
    uvicorn.run(
        "app.main:app",
        host=bind_host,
        port=bind_port,
        reload=use_reload,
    )


def cmd_report(args: argparse.Namespace) -> None:
    """Build the submission package: merge judge, package transcripts, write PDF.

    Guide must (1) write ``docs/judge.md`` and (2) pull every Guide chat into
    ``docs/transcripts/*.md`` before this command. Report only packages those files.
    """
    from app.report_pdf import export_report
    from app.skill_integrity import format_report, verify

    result = export_report(
        name=args.name,
        student_id=args.student_id,
        source=None if args.src is None else Path(args.src),
        output=None if args.output is None else Path(args.output),
    )
    print()
    print("Report package:")
    print(
        f"  Judge:       {'merged docs/judge.md' if result.judge_merged else 'MISSING - Guide must run student-judge first'}"
    )
    print(
        f"  Transcripts: {result.transcript_count} chat(s) in docs/transcripts/"
        + (
            ""
            if result.transcript_count
            else " (EMPTY - Guide must pull Copilot/Cursor/OpenCode chats first)"
        )
    )
    if result.transcript_zip:
        print(f"  Zip:         {result.transcript_zip.as_posix()}")
    print(f"  PDF:         {result.pdf_path.as_posix()}")
    print(format_report(verify()))


def cmd_transcripts(args: argparse.Namespace) -> None:
    """Package agent-written markdown under docs/transcripts/ (+ zip)."""
    from app.transcript_export import package_transcripts

    result = package_transcripts(make_zip=not args.no_zip)
    if result.found == 0:
        print(
            "Warning: no chat markdown in docs/transcripts/. "
            "The Guide agent must pull every Guide chat for this project "
            "(Copilot Agent, Cursor, or OpenCode) into docs/transcripts/<slug>.md first."
        )
        raise SystemExit(2)
    print(f"Submission package ready: {result.out_dir}")
    if result.zip_path:
        print(f"Zip for submission: {result.zip_path}")


def cmd_skills_verify(args: argparse.Namespace) -> None:
    """Check course skill files against .agents/skills.lock.json."""
    from app.skill_integrity import format_report, verify

    result = verify()
    print(format_report(result))
    if not result.ok:
        raise SystemExit(1)


def cmd_usecase(args: argparse.Namespace) -> None:
    """Render docs/diagrams/use-case.json to a UML use-case PNG."""
    from app.usecase_diagram import render_usecase_png

    dest = render_usecase_png(
        spec_path=None if args.spec is None else Path(args.spec),
        output=None if args.output is None else Path(args.output),
    )
    print(f"Wrote {dest}")


def cmd_skills_lock(args: argparse.Namespace) -> None:
    """Rewrite the skill lockfile (course authors only)."""
    from app.skill_integrity import write_lock

    dest = write_lock()
    print(f"Wrote {dest}")


def cmd_users(args: argparse.Namespace) -> None:
    """List users currently in the database."""
    from sqlmodel import select

    from app.database import get_cli_session
    from app.models.user import User

    _ensure_models_loaded()
    with get_cli_session() as session:
        users = session.exec(select(User)).all()
        if not users:
            print("No users found. Run: python manage.py init")
            return
        for user in users:
            print(
                f"  id={user.id}  username={user.username}  "
                f"role={user.role}  email={user.email}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python manage.py",
        description="FastStarter Python CLI — init database, seed demo data, run the app.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init",
        help="Create DB tables and seed demo data (drops existing tables by default)",
    )
    p_init.add_argument(
        "--no-drop",
        dest="drop",
        action="store_false",
        help="Create tables without dropping existing ones",
    )
    p_init.add_argument(
        "--no-seed",
        dest="seed",
        action="store_false",
        help="Skip demo-data seed after creating tables",
    )
    p_init.set_defaults(drop=True, seed=True, func=cmd_init)

    p_seed = sub.add_parser(
        "seed",
        help="Insert demo users and sample degree progress (idempotent; also runs as part of init)",
    )
    p_seed.set_defaults(func=cmd_seed)

    p_run = sub.add_parser("run", help="Start the web app (uvicorn)")
    p_run.add_argument("--host", default=None, help="Bind host")
    p_run.add_argument("--port", type=int, default=None, help="Bind port")
    reload_group = p_run.add_mutually_exclusive_group()
    reload_group.add_argument(
        "--reload", dest="reload", action="store_true", default=None, help="Enable auto-reload"
    )
    reload_group.add_argument(
        "--no-reload", dest="reload", action="store_false", help="Disable auto-reload"
    )
    p_run.set_defaults(func=cmd_run, reload=None)

    p_users = sub.add_parser("users", help="List users in the database")
    p_users.set_defaults(func=cmd_users)

    p_report = sub.add_parser(
        "report",
        help=(
            "Build submission package: merge docs/judge.md, package docs/transcripts/, "
            "write docs/report.pdf (Guide pulls chats + runs student-judge first)"
        ),
    )
    p_report.add_argument("--name", required=True, help="Student name (printed on the PDF cover)")
    p_report.add_argument("--id", dest="student_id", required=True, help="Student ID (PDF only)")
    p_report.add_argument("--src", default=None, help="Markdown path (default: docs/report.md)")
    p_report.add_argument("--output", default=None, help="PDF path (default: docs/report.pdf)")
    p_report.set_defaults(func=cmd_report)

    p_transcripts = sub.add_parser(
        "transcripts",
        help="Package agent-written docs/transcripts/*.md into INDEX + zip (no IDE scrape)",
    )
    p_transcripts.add_argument(
        "--no-zip",
        action="store_true",
        help="Skip writing docs/transcripts.zip",
    )
    p_transcripts.set_defaults(func=cmd_transcripts)

    p_usecase = sub.add_parser(
        "usecase",
        help="Render docs/diagrams/use-case.json to a UML use-case PNG",
    )
    p_usecase.add_argument("--spec", default=None, help="JSON spec (default: docs/diagrams/use-case.json)")
    p_usecase.add_argument("--output", default=None, help="PNG path (default: docs/diagrams/use-case.png)")
    p_usecase.set_defaults(func=cmd_usecase)

    p_skills_verify = sub.add_parser(
        "skills-verify",
        help="Check course skills against .agents/skills.lock.json",
    )
    p_skills_verify.set_defaults(func=cmd_skills_verify)

    p_skills_lock = sub.add_parser(
        "skills-lock",
        help="Rewrite .agents/skills.lock.json (course authors; needs FASTSTARTER_SKILLS_LOCK=1)",
    )
    p_skills_lock.set_defaults(func=cmd_skills_lock)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
