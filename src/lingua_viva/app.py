from __future__ import annotations


async def run_teacher_query(
    query: str,
    intent: str | None = None,
    session_id: str | None = None,
    eval_mode: bool = False,
):
    """Temporary Phase 2 bridge from the web app to Lingua Viva reasoning.

    The old pipeline shell still supplies classification, retrieval, memory,
    and education EXECUTE wiring. The model call itself is routed through the
    native Lingua Viva ReasoningEngine.
    """
    from src.education.pipeline_execute import EducationExecutor
    from src.lingua_viva.ingest import document_retriever
    from src.lingua_viva.reasoning import ReasoningEngine
    from src.pipeline import Pipeline

    retriever = document_retriever()
    pipeline = Pipeline(
        reasoning=ReasoningEngine(),
        document_retriever=retriever,
        education_executor=EducationExecutor(document_retriever=retriever),
    )
    return await pipeline.run(
        query,
        intent=intent,
        session_id=session_id,
        eval_mode=eval_mode,
    )
