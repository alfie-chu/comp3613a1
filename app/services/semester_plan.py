from datetime import date
from typing import Any

from app.repositories.semester_plan import SemesterPlanRepository
from app.models.degree_progress import Semester
from app.models.semester_plan import SemesterPlan
from app.models.student import Student


class StudentProfileMissingError(LookupError):
    pass


class SemesterPlanNotFoundError(LookupError):
    pass


class SemesterPlanNotEditableError(ValueError):
    pass


class SemesterPlanNotDeletableError(ValueError):
    pass


class SemesterPlanService:
    def __init__(self, repository: SemesterPlanRepository):
        self.repository = repository

    def get_editor_data(
        self,
        user_id: int,
        search_query: str = "",
        plan_id: int | None = None,
        semester_id: int | None = None,
        academic_year: int | None = None,
        semester_number: int | None = None,
    ) -> dict[str, Any]:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            return {
                "student": None,
                "plans": [],
                "semesters": [],
                "academic_years": [],
                "semester_terms": {},
                "course_offerings": [],
                "message": "No student record found for the given user ID.",
            }

        today = date.today()
        academic_year_start = today.year if today.month >= 8 else today.year - 1
        semesters = self.repository.ensure_planning_semesters(
            self._build_planning_semesters(academic_year_start, years=5)
        )
        plans = self.repository.get_semester_plans_by_student_id(student.id)
        available_semesters = [
            semester for semester in semesters if semester.end_date >= today
        ]
        plans_by_semester: dict[int | None, SemesterPlan] = {}
        for plan, semester in plans:
            if plan.status in {"planning", "draft", "revision_required"}:
                plans_by_semester.setdefault(semester.id, plan)
        if plan_id is not None:
            _, requested_plan = self._get_owned_plan(user_id, plan_id)
            requested_semester = self.repository.get_semester(
                requested_plan.semester_id
            )
            if requested_semester is None:
                raise SemesterPlanNotFoundError(
                    "The semester for this plan was not found."
                )
            current_plan_row = (requested_plan, requested_semester)
        elif (
            semester_id is not None
            or academic_year is not None
            or semester_number is not None
        ):
            requested_semester = next(
                (
                    semester
                    for semester in available_semesters
                    if (semester_id is None or semester.id == semester_id)
                    and (academic_year is None or semester.year == academic_year)
                    and (
                        semester_number is None
                        or self._semester_number(semester.semester_name)
                        == semester_number
                    )
                ),
                None,
            )
            if requested_semester is None:
                raise SemesterPlanNotFoundError(
                    "Choose a current or future semester."
                )
            current_plan_row = (
                plans_by_semester.get(requested_semester.id),
                requested_semester,
            )
        else:
            default_semester = next(
                (
                    semester
                    for semester in available_semesters
                    if semester.id not in plans_by_semester
                ),
                None,
            ) or next(
                (
                    semester
                    for semester in available_semesters
                    if plans_by_semester[semester.id].status
                    in {"draft", "revision_required"}
                ),
                available_semesters[0] if available_semesters else None,
            )
            current_plan_row = (
                (
                    plans_by_semester.get(default_semester.id),
                    default_semester,
                )
                if default_semester is not None
                else None
            )
        current_plan, current_semester = (
            current_plan_row if current_plan_row is not None else (None, None)
        )

        if current_plan is not None and current_semester is not None:
            semester_ids = [current_semester.id]
            selected_offerings = self.repository.get_selected_offerings(
                current_plan.id
            )
            latest_approval_request = self.repository.get_latest_approval_request(
                current_plan.id
            )
        else:
            semester_ids = (
                [current_semester.id] if current_semester is not None else []
            )
            selected_offerings = []
            latest_approval_request = None

        course_offerings = self.repository.get_course_offerings_by_semester_ids(
            semester_ids,
            search_query,
            self.repository.get_programme_course_ids_for_student(student.id),
        )
        selected_course_ids = {
            offering.course_id for _, offering, _ in selected_offerings
        }
        course_offerings = [
            (offering, course)
            for offering, course in course_offerings
            if course.id not in selected_course_ids
        ]
        planned_credits = sum(
            course.credits for _, _, course in selected_offerings
        )

        return {
            "student": student,
            "plans": plans,
            "semesters": available_semesters,
            "academic_years": sorted(
                {semester.year for semester in available_semesters}
            ),
            "term_years": {
                number: sorted(
                    {
                        semester.year
                        for semester in available_semesters
                        if self._semester_number(semester.semester_name) == number
                    }
                )
                for number in (1, 2, 3)
            },
            "semester_number": (
                self._semester_number(current_semester.semester_name)
                if current_semester is not None
                else None
            ),
            "course_offerings": course_offerings,
            "current_plan": current_plan,
            "current_semester": current_semester,
            "latest_approval_request": latest_approval_request,
            "selected_offerings": selected_offerings,
            "planned_credits": planned_credits,
            "search_query": search_query,
            "message": None,
        }

    @staticmethod
    def _build_planning_semesters(
        first_academic_year: int,
        years: int,
    ) -> list[Semester]:
        semesters = []
        for year in range(first_academic_year, first_academic_year + years):
            next_year = year + 1
            semesters.extend(
                (
                    Semester(
                        semester_name=f"Semester 1 {year}/{next_year}",
                        year=year,
                        start_date=date(year, 8, 17),
                        end_date=date(year, 12, 18),
                    ),
                    Semester(
                        semester_name=f"Semester 2 {year}/{next_year}",
                        year=year,
                        start_date=date(next_year, 1, 12),
                        end_date=date(next_year, 5, 1),
                    ),
                    Semester(
                        semester_name=f"Semester 3 {year}/{next_year}",
                        year=year,
                        start_date=date(next_year, 5, 15),
                        end_date=date(next_year, 8, 5),
                    ),
                )
            )
        return semesters

    @staticmethod
    def _semester_number(semester_name: str) -> int | None:
        parts = semester_name.split()
        if len(parts) < 2 or parts[0] != "Semester":
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    def get_dashboard_summary(self, user_id: int) -> dict[str, Any]:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            return {"student": None}

        current_plan_row = self.repository.get_current_semester_plan(student.id)
        if current_plan_row is None:
            return {"student": student, "plan": None}
        plan, semester = current_plan_row
        editor = self.get_editor_data(user_id, plan_id=plan.id)
        return {
            "student": student,
            "plan": plan,
            "semester": semester,
            "planned_credits": editor["planned_credits"],
            "can_edit": plan.status in {"planning", "draft", "revision_required"},
        }

    def get_my_plans_data(self, user_id: int) -> dict[str, Any]:
        editor = self.get_editor_data(user_id)
        existing_semester_ids = {
            semester.id for _, semester in editor["plans"]
        }
        return {
            "student": editor["student"],
            "plans": [
                (plan, semester)
                for plan, semester in editor["plans"]
                if plan.status != "planning"
            ],
            "available_semesters": [
                semester
                for semester in editor["semesters"]
                if semester.id not in existing_semester_ids
            ],
            "message": editor["message"],
        }

    def get_plan_detail(self, user_id: int, plan_id: int) -> dict[str, Any]:
        student, plan = self._get_owned_plan(user_id, plan_id)
        semester = self.repository.get_semester(plan.semester_id)
        if semester is None:
            raise SemesterPlanNotFoundError("The semester for this plan was not found.")
        selected_offerings = self.repository.get_selected_offerings(plan.id)
        latest_approval_request = self.repository.get_latest_approval_request(plan.id)
        return {
            "student": student,
            "plan": plan,
            "semester": semester,
            "selected_offerings": selected_offerings,
            "latest_approval_request": latest_approval_request,
            "planned_credits": sum(
                course.credits for _, _, course in selected_offerings
            ),
            "can_edit": plan.status
            in {"planning", "draft", "revision_required"},
        }

    def get_summary_data(self, user_id: int, plan_id: int) -> dict[str, Any]:
        data = self.get_plan_detail(user_id, plan_id)
        completed_course_ids = self.repository.get_completed_course_ids(
            data["student"].id
        )
        warnings = []
        for _, _, course in data["selected_offerings"]:
            if course.id is None:
                continue
            prerequisite_ids = self.repository.get_prerequisite_course_ids(
                course.id
            )
            for prerequisite_id in prerequisite_ids:
                if prerequisite_id in completed_course_ids:
                    continue
                prerequisite = self.repository.get_course(prerequisite_id)
                if prerequisite is not None:
                    warnings.append(
                        {
                            "course_code": course.course_code,
                            "prerequisite_code": prerequisite.course_code,
                        }
                    )
        data["prerequisite_warnings"] = warnings
        data["requirements_satisfied"] = not warnings
        return data

    def start_plan(self, user_id: int, semester_id: int) -> SemesterPlan:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            raise StudentProfileMissingError("No student profile is linked to this account.")

        semester = self.repository.get_semester(semester_id)
        if semester is None or semester.end_date < date.today():
            raise SemesterPlanNotFoundError("Choose a current or future semester.")

        existing_plan = self.repository.get_plan_for_student_semester(
            student.id,
            semester_id,
        )
        if existing_plan is not None:
            return existing_plan
        return self.repository.create_plan(student.id, semester_id)

    def delete_draft_plan(self, user_id: int, plan_id: int) -> None:
        student, plan = self._get_owned_plan(user_id, plan_id)
        if plan.status != "draft":
            raise SemesterPlanNotDeletableError(
                "Only draft plans may be deleted."
            )
        self.repository.delete_draft_plan(plan)

    def add_course(
        self,
        user_id: int,
        plan_id: int,
        offering_id: int,
    ) -> None:
        student, plan = self._get_owned_plan(user_id, plan_id)
        self._ensure_editable(plan)
        offering_row = self.repository.get_offering(offering_id)
        if offering_row is None:
            raise SemesterPlanNotFoundError("The selected course offering was not found.")
        offering, course = offering_row
        if offering.semester_id != plan.semester_id or offering.status != "open":
            raise SemesterPlanNotEditableError(
                "This course offering is not available for the selected semester."
            )

        selected_offerings = self.repository.get_selected_offerings(plan.id)
        if any(existing_course.id == course.id for _, _, existing_course in selected_offerings):
            raise SemesterPlanNotEditableError(
                f"{course.course_code} is already in this semester plan."
            )
        self.repository.add_course_selection(plan.id, offering.id)

    def remove_course(
        self,
        user_id: int,
        plan_id: int,
        selection_id: int,
    ) -> None:
        _, plan = self._get_owned_plan(user_id, plan_id)
        self._ensure_editable(plan)
        if not self.repository.remove_course_selection(plan.id, selection_id):
            raise SemesterPlanNotFoundError("The selected course was not found in this plan.")

    def save_draft(self, user_id: int, plan_id: int) -> SemesterPlan:
        _, plan = self._get_owned_plan(user_id, plan_id)
        self._ensure_editable(plan)
        return self.repository.save_draft(plan)

    def submit_for_review(self, user_id: int, plan_id: int) -> SemesterPlan:
        _, plan = self._get_owned_plan(user_id, plan_id)
        self._ensure_editable(plan)
        if not self.repository.get_selected_offerings(plan.id):
            raise SemesterPlanNotEditableError(
                "Add at least one course before submitting this plan."
            )
        return self.repository.submit_plan(plan)

    def _get_owned_plan(
        self,
        user_id: int,
        plan_id: int,
    ) -> tuple[Student, SemesterPlan]:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            raise StudentProfileMissingError(
                "No student profile is linked to this account."
            )
        plan = self.repository.get_plan_for_student(plan_id, student.id)
        if plan is None:
            raise SemesterPlanNotFoundError("Semester plan not found.")
        return student, plan

    @staticmethod
    def _ensure_editable(plan: SemesterPlan) -> None:
        if plan.status not in {"planning", "draft", "revision_required"}:
            raise SemesterPlanNotEditableError(
                "This semester plan is no longer editable."
            )
