import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from simulator.tick_loop import get_simulator

router = APIRouter(prefix="/ws", tags=["Websocket"])

@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """
    Stream all 4 machines every 100ms (10 Hz).
    Connect to ws://<host>/ws/live
    """
    await websocket.accept()
    sim = get_simulator()
    
    try:
        while True:
            # Get the snapshot from the simulator
            data = sim.get_live_snapshot()
            
            # Send the JSON payload
            await websocket.send_json(data)
            
            # Sleep for 100ms (10 Hz)
            await asyncio.sleep(0.1)
            
    except WebSocketDisconnect:
        # Client disconnected normally
        pass
    except Exception as e:
        # Handle other unexpected drops
        print(f"WebSocket Error: {e}")
