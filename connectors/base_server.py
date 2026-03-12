from fastapi import FastAPI
import uvicorn
from abc import abstractmethod
import os

class BaseConnectorServer:
    def __init__(self, port: int, source_type: str):
        self.port = port
        self.source_type = source_type
        self.app = FastAPI()
        self.app.get("/health")(self.health)
        self.app.get("/data")(self.fetch_data)

    async def health(self):
        return {"status": "ok", "source": self.source_type}

    @abstractmethod
    async def fetch_data(self, entity_id: str, start_ts: float, end_ts: float):
        ...

    def run(self):
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)