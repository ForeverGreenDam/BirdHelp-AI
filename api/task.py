from celery.result import AsyncResult

from fastapi import APIRouter

from core.schemas import TaskStatus, TaskStatusResponse

router = APIRouter(prefix="/ai/task", tags=["task"])


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str):
    result = AsyncResult(task_id)
    mapping = {
        "PENDING": TaskStatus.pending,
        "STARTED": TaskStatus.processing,
        "SUCCESS": TaskStatus.completed,
        "FAILURE": TaskStatus.failed,
    }
    status = mapping.get(result.state, TaskStatus.pending)

    file_url = None
    error = None
    if status == TaskStatus.completed and result.result:
        file_url = result.result.get("file_url")
    if status == TaskStatus.failed:
        error = str(result.info) if result.info else "Unknown error"

    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        file_url=file_url,
        error=error,
    )
