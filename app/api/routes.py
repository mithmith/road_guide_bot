from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.schemas import ChatRequest, ChatResponse, HealthResponse, RouteResponse
from app.services.chat import ChatService

router = APIRouter()


def get_chat_service(request: Request) -> ChatService:
    svc = getattr(request.app.state, "chat_service", None)
    if svc is None:
        raise HTTPException(status_code=500, detail="ChatService is not initialized")
    return svc


@router.get("/health", response_model=HealthResponse)
def healthcheck():
    return HealthResponse()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, svc: ChatService = Depends(get_chat_service)):
    result = svc.chat(user_text=req.user_text, conversation_id=req.conversation_id)
    return ChatResponse(
        conversation_id=result.conversation_id,
        assistant_text=result.assistant_text,
        response_id=result.response_id,
    )


# -------------------- Эндпоинт --------------------


@app.post("/route", response_model=RouteResponse)
async def route(req: RouteRequest) -> RouteResponse:
    try:
        a_lat, a_lon, a_label = await ensure_coords(req.a)
        b_lat, b_lon, b_label = await ensure_coords(req.b)

        data = await ors_route(a_lat, a_lon, b_lat, b_lon, req.options or OptionsIn())
        steps, total_m, total_s, coords, step_bounds = ors_extract_steps(data)

        if not steps:
            return RouteResponse(
                ok=False, type="error", message="Маршрут пуст (нет шагов)"
            )

        # Обогащаем locality и добавляем промежуточные населённые пункты на длинных шагах
        await enrich_localities_with_yandex(steps)
        await annotate_intermediate_localities(
            steps, step_bounds, coords, min_step_m=5000, sample_interval_m=5000
        )

        md = build_markdown(
            a_label, a_lat, a_lon, b_label, b_lat, b_lon, steps, total_m, total_s
        )
        return RouteResponse(ok=True, markdown=md, steps=steps)

    except HTTPException as he:
        return RouteResponse(ok=False, type="error", message=str(he.detail))
    except Exception as e:
        logger.exception("unexpected error")
        return RouteResponse(ok=False, type="error", message=f"Неожиданная ошибка: {e}")
