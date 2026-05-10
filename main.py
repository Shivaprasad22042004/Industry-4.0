from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import endpoints, websocket, analytics
from simulator.tick_loop import get_simulator
from database import db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the 10 Hz simulator loop
    print("Starting Industry 4.0 Simulator Engine...")
    await db.init_db()
    sim = get_simulator()
    await sim.start()
    
    yield
    
    # Shutdown: Stop the loop cleanly
    print("Shutting down Simulator Engine...")
    await sim.stop()
    await db.close_db()


app = FastAPI(
    title="Industry 4.0 Data Simulator",
    description="Physics-based telemetry simulator for industrial machines",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev. Restrict in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST endpoints
app.include_router(endpoints.router)
app.include_router(analytics.router)

# Mount WebSocket endpoint
app.include_router(websocket.router)

@app.get("/")
async def root():
    return {
        "message": "Industry 4.0 Data Simulator is running",
        "endpoints": {
            "REST": "/machines",
            "WebSocket": "/ws/live"
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Standard entry point for local dev
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
