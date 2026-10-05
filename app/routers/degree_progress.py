from fastapi import Request
from fastapi.responses import HTMLResponse

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.repositories.degree_progress import DegreeProgressRepository
from app.services.degree_progress import DegreeProgressService
from . import router, templates


@router.get("/degree", response_class=HTMLResponse, name="degree_progress_view")
async def degree_progress_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    repository = DegreeProgressRepository(db)
    service = DegreeProgressService(repository)
    progress = service.get_progress_for_student(user.id)

    return templates.TemplateResponse(
        request=request,
        name="degree-progress.html",
        context={"user": user, "progress": progress},
    )
