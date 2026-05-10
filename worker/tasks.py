from worker.celery_app import app


@app.task(bind=True)
def generate_ppt_task(self, params: dict) -> dict:
    """占位 — Phase 3 实现。"""
    return {"status": "completed", "task_id": self.request.id}


@app.task(bind=True)
def generate_word_task(self, params: dict) -> dict:
    """占位 — Phase 3 实现。"""
    return {"status": "completed", "task_id": self.request.id}


@app.task(bind=True)
def generate_pdf_task(self, params: dict) -> dict:
    """占位 — Phase 3 实现。"""
    return {"status": "completed", "task_id": self.request.id}
