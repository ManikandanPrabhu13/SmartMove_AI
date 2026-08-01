"""
manager.py

Handles WebSocket connections.
"""

from fastapi import WebSocket


class ConnectionManager:

    def __init__(self):

        self.active_connections = []


    async def connect(self, websocket: WebSocket):

        await websocket.accept()

        self.active_connections.append(websocket)


    def disconnect(self, websocket: WebSocket):

        self.active_connections.remove(websocket)


    async def broadcast(self, message):

        dead_connections = []

        for connection in self.active_connections:

            try:
                await connection.send_json(message)

            except Exception:
                dead_connections.append(connection)

        for connection in dead_connections:

            if connection in self.active_connections:
                self.active_connections.remove(connection)


manager = ConnectionManager()