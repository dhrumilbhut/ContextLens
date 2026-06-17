import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.models.projects import (
    ProblemDocument,
    ProjectCreate,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListItem,
    ProjectListResponse,
)
from app.services.project_service import (
    create_project,
    delete_project,
    get_project,
    list_projects,
)

router = APIRouter()


@router.post("/projects", status_code=201, response_model=ProjectCreateResponse)
async def post_project(
    body: ProjectCreate,
    conn: asyncpg.Connection = Depends(get_db),
):
    project = await create_project(conn, body.name, body.description)
    return ProjectCreateResponse(**project)


@router.get("/projects", response_model=ProjectListResponse)
async def get_projects(conn: asyncpg.Connection = Depends(get_db)):
    projects = await list_projects(conn)
    items = [
        ProjectListItem(
            id=p["id"],
            name=p["name"],
            description=p["description"],
            trace_count=p["trace_count"] or 0,
            avg_faithfulness=(
                float(p["avg_faithfulness"]) if p["avg_faithfulness"] is not None else None
            ),
            created_at=p["created_at"],
        )
        for p in projects
    ]
    return ProjectListResponse(projects=items)


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project_detail(
    project_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    project = await get_project(conn, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetailResponse(
        id=project["id"],
        name=project["name"],
        trace_count=project["trace_count"],
        avg_faithfulness_7d=project["avg_faithfulness_7d"],
        unfaithful_claim_rate=project["unfaithful_claim_rate"],
        top_problem_documents=[
            ProblemDocument(**doc) for doc in project["top_problem_documents"]
        ],
    )


@router.delete("/projects/{project_id}")
async def delete_project_route(
    project_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    deleted = await delete_project(conn, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project deleted."}
