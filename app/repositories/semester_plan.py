from datetime import date, datetime

from sqlmodel import Session
from sqlmodel import select

from app.models.degree_progress import (
    Course,
    CourseCompletion,
    CoursePrerequisite,
    Semester,
)
from app.models.approval import ApprovalRequest
from app.models.semester_plan import CourseOffering, CourseSelection, SemesterPlan
from app.models.student import Student

class SemesterPlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_student_by_user_id(self, user_id: int) -> Student | None:
        statement = select(Student).where(Student.user_id == user_id)
        return self.db.exec(statement).one_or_none()

    def get_semester_plans_by_student_id(
        self,
        student_id: int,
    ) -> list[tuple[SemesterPlan, Semester]]:
        statement = (
            select(SemesterPlan, Semester)
            .join(Semester, SemesterPlan.semester_id == Semester.id)
            .where(SemesterPlan.student_id == student_id)
            .order_by(Semester.start_date.desc(), SemesterPlan.created_at.desc())
        )
        return list(self.db.exec(statement).all())

    def get_all_semesters(self) -> list[Semester]:
        statement = select(Semester).order_by(Semester.start_date)
        return list(self.db.exec(statement).all())

    def ensure_planning_semesters(
        self,
        semesters: list[Semester],
    ) -> list[Semester]:
        existing_semesters = self.get_all_semesters()
        existing_keys = {
            (semester.year, semester.semester_name)
            for semester in existing_semesters
        }
        changed = False

        for semester in semesters:
            key = (semester.year, semester.semester_name)
            if key not in existing_keys:
                self.db.add(semester)
                existing_semesters.append(semester)
                existing_keys.add(key)
                changed = True

        if changed:
            self.db.flush()

        template_offerings: list[CourseOffering] = []
        offering_rows = self.db.exec(
            select(CourseOffering, Semester.start_date)
            .join(Semester, CourseOffering.semester_id == Semester.id)
            .where(CourseOffering.status == "open")
            .order_by(Semester.start_date, CourseOffering.id)
        ).all()
        if offering_rows:
            template_semester_id = offering_rows[0][0].semester_id
            template_offerings = [
                offering
                for offering, _ in offering_rows
                if offering.semester_id == template_semester_id
            ]

        for semester in semesters:
            if semester.id is None:
                continue
            existing_offering = self.db.exec(
                select(CourseOffering.id)
                .where(CourseOffering.semester_id == semester.id)
                .limit(1)
            ).first()
            if existing_offering is not None or not template_offerings:
                continue

            self.db.add_all(
                CourseOffering(
                    course_id=offering.course_id,
                    semester_id=semester.id,
                    section=offering.section,
                    delivery_mode=offering.delivery_mode,
                    status="open",
                )
                for offering in template_offerings
            )
            changed = True

        if changed:
            self.db.commit()
            existing_semesters = self.get_all_semesters()

        return existing_semesters

    def get_course_offerings_by_semester_ids(
        self,
        semester_ids: list[int],
        search_query: str = "",
    ) -> list[tuple[CourseOffering, Course]]:
        if not semester_ids:
            return []

        statement = (
            select(CourseOffering, Course)
            .join(Course, CourseOffering.course_id == Course.id)
            .where(
                CourseOffering.semester_id.in_(semester_ids),
                CourseOffering.status == "open",
            )
            .order_by(Course.course_code, CourseOffering.section)
        )
        if search_query:
            pattern = f"%{search_query.strip()}%"
            statement = statement.where(
                Course.course_code.ilike(pattern) | Course.title.ilike(pattern)
            )
        return list(self.db.exec(statement).all())

    def get_current_semester_plan(
        self,
        student_id: int,
        today: date | None = None,
    ) -> tuple[SemesterPlan, Semester] | None:
        current_date = today or date.today()
        statement = (
            select(SemesterPlan, Semester)
            .join(Semester, SemesterPlan.semester_id == Semester.id)
            .where(
                SemesterPlan.student_id == student_id,
                Semester.end_date >= current_date,
                SemesterPlan.status != "planning",
            )
            .order_by(Semester.start_date, SemesterPlan.created_at.desc())
        )
        return self.db.exec(statement).first()

    def get_plan_for_student(
        self,
        plan_id: int,
        student_id: int,
    ) -> SemesterPlan | None:
        statement = select(SemesterPlan).where(
            SemesterPlan.id == plan_id,
            SemesterPlan.student_id == student_id,
        )
        return self.db.exec(statement).one_or_none()

    def get_plan_for_student_semester(
        self,
        student_id: int,
        semester_id: int,
    ) -> SemesterPlan | None:
        statement = (
            select(SemesterPlan)
            .where(
                SemesterPlan.student_id == student_id,
                SemesterPlan.semester_id == semester_id,
                SemesterPlan.status.in_(
                    ("planning", "draft", "revision_required")
                ),
            )
            .order_by(SemesterPlan.created_at.desc())
        )
        return self.db.exec(statement).first()

    def get_semester(self, semester_id: int) -> Semester | None:
        return self.db.get(Semester, semester_id)

    def get_latest_approval_request(
        self,
        plan_id: int,
    ) -> ApprovalRequest | None:
        statement = (
            select(ApprovalRequest)
            .where(ApprovalRequest.semester_plan_id == plan_id)
            .order_by(ApprovalRequest.submitted_at.desc())
        )
        return self.db.exec(statement).first()

    def get_offering(
        self,
        offering_id: int,
    ) -> tuple[CourseOffering, Course] | None:
        statement = (
            select(CourseOffering, Course)
            .join(Course, CourseOffering.course_id == Course.id)
            .where(CourseOffering.id == offering_id)
        )
        return self.db.exec(statement).one_or_none()

    def get_selected_offerings(
        self,
        plan_id: int,
    ) -> list[tuple[CourseSelection, CourseOffering, Course]]:
        statement = (
            select(CourseSelection, CourseOffering, Course)
            .join(
                CourseOffering,
                CourseSelection.course_offering_id == CourseOffering.id,
            )
            .join(Course, CourseOffering.course_id == Course.id)
            .where(CourseSelection.semester_plan_id == plan_id)
            .order_by(Course.course_code, CourseOffering.section)
        )
        return list(self.db.exec(statement).all())

    def get_completed_course_ids(self, student_id: int) -> set[int]:
        statement = select(CourseCompletion.course_id).where(
            CourseCompletion.student_id == student_id
        )
        return set(self.db.exec(statement).all())

    def get_course(self, course_id: int) -> Course | None:
        return self.db.get(Course, course_id)

    def get_prerequisite_course_ids(self, course_id: int) -> list[int]:
        statement = select(CoursePrerequisite.prerequisite_course_id).where(
            CoursePrerequisite.course_id == course_id
        )
        return list(self.db.exec(statement).all())

    def create_plan(self, student_id: int, semester_id: int) -> SemesterPlan:
        plan = SemesterPlan(student_id=student_id, semester_id=semester_id)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def delete_draft_plan(self, plan: SemesterPlan) -> None:
        statement = select(CourseSelection).where(CourseSelection.semester_plan_id == plan.id)
        selections = self.db.exec(statement).all()

        for s in selections:
            self.db.delete(s)

        self.db.delete(plan)
        self.db.commit()

    def add_course_selection(
        self,
        plan_id: int,
        offering_id: int,
    ) -> CourseSelection:
        statement = select(CourseSelection).where(
            CourseSelection.semester_plan_id == plan_id,
            CourseSelection.course_offering_id == offering_id,
        )
        selection = self.db.exec(statement).one_or_none()
        if selection is not None:
            return selection

        selection = CourseSelection(
            semester_plan_id=plan_id,
            course_offering_id=offering_id,
        )
        self.db.add(selection)
        self.db.commit()
        self.db.refresh(selection)
        return selection

    def remove_course_selection(self, plan_id: int, selection_id: int) -> bool:
        statement = select(CourseSelection).where(
            CourseSelection.id == selection_id,
            CourseSelection.semester_plan_id == plan_id,
        )
        selection = self.db.exec(statement).one_or_none()
        if selection is None:
            return False
        self.db.delete(selection)
        self.db.commit()
        return True

    def save_draft(self, plan: SemesterPlan) -> SemesterPlan:
        plan.status = "draft"
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def submit_plan(self, plan: SemesterPlan) -> SemesterPlan:
        plan.status = "under_review"
        plan.submitted_at = datetime.now()
        approval_request = ApprovalRequest(
            semester_plan_id=plan.id,
            status="pending",
            submitted_at=plan.submitted_at,
        )
        self.db.add(plan)
        self.db.add(approval_request)
        self.db.commit()
        self.db.refresh(plan)
        return plan
