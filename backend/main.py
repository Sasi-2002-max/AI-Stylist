from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from backend.database.connection import engine
from backend.fitting_room.schemas import FittingRoomRequest, FittingRoomResponse
from backend.fitting_room.service import FittingRoomService, InvalidMannequinGenderError

app = FastAPI(title="AI Fashion Stylist API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/db-test")
def database_test():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))

            return {
                "status": "success",
                "database": "connected",
                "result": result.scalar(),
            }

    except Exception as e:
        return {
            "status": "error",
            "database": "connection_failed",
            "error": str(e),
        }


@app.post("/api/fitting-room", response_model=FittingRoomResponse)
async def fitting_room(request: FittingRoomRequest) -> FittingRoomResponse:
    """
    Part 42: resolve an already-selected outfit (Part 41's build_outfit()
    output) into fitting-room data -- mannequin + real product details,
    color variations, and alternatives -- for the future Next.js frontend.
    """
    service = FittingRoomService()
    try:
        return await service.prepare_fitting_room(
            outfit_result=request.outfit,
            mannequin_gender=request.mannequin_gender,
            include_variants=request.include_variants,
            include_alternatives=request.include_alternatives,
        )
    except InvalidMannequinGenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc