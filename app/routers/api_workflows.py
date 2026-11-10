"""JSON API endpoints for COMP 3613 Assignment 2 Postman tests.

Add `api_workflows` to the import list at the end of app/routers/__init__.py.
Reuses the existing services and repository methods; does not replace HTML routes.
"""
from pydantic import BaseModel
from fastapi import HTTPException, Response, status

from app.dependencies.auth import AuthDep, AdminDep
from app.dependencies.session import SessionDep
from app.repositories.user import UserRepository
from app.repositories.degree_progress import DegreeProgressRepository
from app.repositories.semester_plan import SemesterPlanRepository
from app.repositories.approval import ApprovalRepository
from app.services.auth_service import AuthService
from app.services.degree_progress import DegreeProgressService
from app.services.semester_plan import (
    SemesterPlanService, StudentProfileMissingError, SemesterPlanNotFoundError,
    SemesterPlanNotEditableError,
)
from app.services.approval import (
    ApprovalService, AdvisorProfileMissingError,
    ApprovalDecisionValidationError, ApprovalRequestAlreadyReviewedError,
    ApprovalRequestNotFoundError,
)
from app.utilities.security import access_token_cookie_kwargs
from . import api_router


class LoginPayload(BaseModel):
    username: str
    password: str


class CompletionPayload(BaseModel):
    course_id: int
    grade: str
    academic_year: int
    semester_number: int


class CreatePlanPayload(BaseModel):
    semester_id: int


class AddOfferingPayload(BaseModel):
    offering_id: int


class ReviewPayload(BaseModel):
    outcome: str
    comments: str = ""


@api_router.post('/auth/login', tags=['MyAdvisor Workflow API'])
def api_login(body: LoginPayload, response: Response, db: SessionDep):
    repo = UserRepository(db)
    token = AuthService(repo).authenticate_user(body.username, body.password)
    if not token:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    user = repo.get_by_username(body.username)
    response.set_cookie('access_token', token, **access_token_cookie_kwargs())
    return {'message': 'Login successful', 'username': user.username, 'role': user.role}


@api_router.post('/auth/logout', tags=['MyAdvisor Workflow API'])
def api_logout(response: Response):
    response.delete_cookie('access_token')
    return {'message': 'Logged out'}


@api_router.get('/degree/progress', tags=['MyAdvisor Workflow API'])
def api_degree_progress(user: AuthDep, db: SessionDep):
    progress = DegreeProgressService(DegreeProgressRepository(db)).get_progress_for_student(user.id)
    if progress is None:
        raise HTTPException(status_code=404, detail='Student profile not found')
    return progress


@api_router.get('/degree/available-courses', tags=['MyAdvisor Workflow API'])
def api_available_completion_courses(user: AuthDep, db: SessionDep):
    service = DegreeProgressService(DegreeProgressRepository(db))
    courses, years = service.get_course_completion_form_data(user.id)
    if not years:
        raise HTTPException(status_code=404, detail='Student degree profile not found')
    return {
        'courses': [
            {'id': course.id, 'course_code': course.course_code, 'title': course.title}
            for course in courses
        ],
        'academic_years': years,
    }


@api_router.post('/degree/completions', status_code=status.HTTP_201_CREATED,
                 tags=['MyAdvisor Workflow API'])
def api_add_completion(body: CompletionPayload, user: AuthDep, db: SessionDep):
    service = DegreeProgressService(DegreeProgressRepository(db))
    try:
        completed = service.add_course_completion(
            user_id=user.id, course_id=body.course_id, grade=body.grade,
            academic_year=body.academic_year, semester_number=body.semester_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        'id': completed.id,
        'course_id': completed.course_id,
        'grade': completed.grade,
        'academic_year': completed.academic_year,
        'semester_number': completed.semester_number,
    }


@api_router.get('/semester-plans/options', tags=['MyAdvisor Workflow API'])
def api_planning_options(user: AuthDep, db: SessionDep):
    editor = SemesterPlanService(SemesterPlanRepository(db)).get_editor_data(user.id)
    if editor['student'] is None:
        raise HTTPException(status_code=404, detail='Student profile not found')
    semester = editor.get('current_semester')
    return {
        'semester_id': semester.id if semester else None,
        'semesters': [
            {'id': s.id, 'semester_name': s.semester_name}
            for s in editor['semesters']
        ],
        'course_offerings': [
            {'id': offering.id, 'course_id': course.id, 'course_code': course.course_code}
            for offering, course in editor['course_offerings']
        ],
    }


@api_router.post('/semester-plans', tags=['MyAdvisor Workflow API'])
def api_create_plan(body: CreatePlanPayload, response: Response, user: AuthDep, db: SessionDep):
    repo = SemesterPlanRepository(db)
    service = SemesterPlanService(repo)
    try:
        student = repo.get_student_by_user_id(user.id)
        if student is None:
            raise StudentProfileMissingError('Student profile not found')
        previous = repo.get_plan_for_student_semester(student.id, body.semester_id)
        plan = service.start_plan(user.id, body.semester_id)
    except StudentProfileMissingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SemesterPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response.status_code = 200 if previous else 201
    return {'plan_id': plan.id, 'semester_id': plan.semester_id, 'status': plan.status}


@api_router.post('/semester-plans/{plan_id}/courses', status_code=status.HTTP_201_CREATED,
                 tags=['MyAdvisor Workflow API'])
def api_add_plan_course(plan_id: int, body: AddOfferingPayload, user: AuthDep, db: SessionDep):
    service = SemesterPlanService(SemesterPlanRepository(db))
    try:
        service.add_course(user.id, plan_id, body.offering_id)
    except (StudentProfileMissingError, SemesterPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SemesterPlanNotEditableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'message': 'Course added', 'plan_id': plan_id, 'offering_id': body.offering_id}


@api_router.post('/semester-plans/{plan_id}/submit', tags=['MyAdvisor Workflow API'])
def api_submit_plan(plan_id: int, user: AuthDep, db: SessionDep):
    repo = SemesterPlanRepository(db)
    service = SemesterPlanService(repo)
    try:
        plan = service.submit_for_review(user.id, plan_id)
    except (StudentProfileMissingError, SemesterPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SemesterPlanNotEditableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    approval = repo.get_latest_approval_request(plan.id)
    return {
        'plan_id': plan.id,
        'status': plan.status,
        'approval_request_id': approval.id if approval else None,
    }


@api_router.get('/semester-plans/{plan_id}', tags=['MyAdvisor Workflow API'])
def api_plan_detail(plan_id: int, user: AuthDep, db: SessionDep):
    service = SemesterPlanService(SemesterPlanRepository(db))
    try:
        details = service.get_plan_detail(user.id, plan_id)
    except (StudentProfileMissingError, SemesterPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    plan = details['plan']
    return {
        'plan_id': plan.id,
        'status': plan.status,
        'selected_courses': [
            {'offering_id': offering.id, 'course_code': course.course_code}
            for _, offering, course in details['selected_offerings']
        ],
    }


@api_router.get('/admin/approval-requests', tags=['MyAdvisor Workflow API'])
def api_pending_requests(user: AdminDep, db: SessionDep):
    pending = ApprovalService(ApprovalRepository(db)).get_pending_approval_requests()
    return {'requests': [
        {'request_id': item['approval'].id,
         'plan_id': item['plan'].id,
         'status': item['approval'].status}
        for item in pending
    ]}


@api_router.patch('/admin/approval-requests/{request_id}', tags=['MyAdvisor Workflow API'])
def api_review_plan(request_id: int, body: ReviewPayload, user: AdminDep, db: SessionDep):
    try:
        ApprovalService(ApprovalRepository(db)).review_plan(
            user.id, request_id, body.outcome, body.comments,
        )
    except (AdvisorProfileMissingError, ApprovalRequestNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalDecisionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ApprovalRequestAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'request_id': request_id, 'status': body.outcome, 'message': 'Review saved'}