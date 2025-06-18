import asyncio
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import json
from datetime import datetime
import os
from typing import List

#http://localhost:8000/static/index.html


app = FastAPI()


os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop = asyncio.get_event_loop()
        self._running = False

    def _get_cpu_temperature(self):
        """Получаем температуру CPU"""
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if 'coretemp' in temps:
                    # Для Intel CPU
                    return max([x.current for x in temps['coretemp'] if 'Core' in x.label])
                elif 'k10temp' in temps:
                    # Для AMD CPU
                    return temps['k10temp'][0].current
            return None
        except Exception as e:
            print(f"Error getting CPU temperature: {e}")
            return None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        if not self._running:
            self._running = True
            asyncio.create_task(self.metrics_loop())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, metrics: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(metrics))
            except Exception as e:
                print(f"Error sending to client: {e}")
                self.disconnect(connection)

    def get_system_metrics(self):
        """Получение метрик системы"""
        # CPU
        psutil.cpu_percent(interval=0.1)  
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Память
        mem = psutil.virtual_memory()
        
        # Температура CPU
        #cpu_temp = self._get_cpu_temperature()

        # Диск
        disk = psutil.disk_usage('/')
        
        # Сеть
        net = psutil.net_io_counters()
        net_sent = round(net.bytes_sent / (1024 ** 2), 2)     # MB
        net_recv = round(net.bytes_recv / (1024 ** 2), 2)     # MB
        
        return {
            "cpu_usage": cpu_percent,
            #"cpu_temp": cpu_temp,
            "memory_usage": mem.percent,
            "memory_used": round(mem.used / (1024 ** 3), 2),
            "memory_total": round(mem.total / (1024 ** 3), 2),
             "disk_usage": disk.percent,
            "disk_used": round(disk.used / (1024 ** 3), 2),
            "disk_total": round(disk.total / (1024 ** 3), 2),
            "net_sent": net_sent,
            "net_recv": net_recv,
            "timestamp": datetime.now().isoformat()
        }

    async def metrics_loop(self):
        """Цикл сбора и рассылки метрик"""
        while self._running and self.active_connections:
            metrics = self.get_system_metrics()
            await self.broadcast(metrics)
            await asyncio.sleep(1)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print("Client connected via WebSocket")
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received from client: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        manager.disconnect(websocket)

@app.get("/")
async def root():
    return {"message": "System Monitoring Server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, ws_ping_interval=10, ws_ping_timeout=30)