import asyncio
import time

from mcp_server.core.access_control.domain import Principal


def principal(subject="developer"):
    return Principal("https://test.auth0.com/", subject, time.time() + 3600)


class MemoryAudit:
    def __init__(self, fail=None):
        self.operations = []
        self.events = []
        self.fail = fail

    async def start(self, operation):
        if self.fail == "start":
            raise OSError("offline")
        self.operations.append(operation)

    async def event(self, operation_id, kind, detail):
        if self.fail == kind:
            raise OSError("offline")
        self.events.append((operation_id, kind, detail))


class Approver:
    def __init__(self, decision="approved", callback=None, delay=0):
        self.decision, self.callback, self.delay = decision, callback, delay
        self.messages = []

    async def request(self, message):
        self.messages.append(message)
        if self.callback:
            self.callback()
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.decision
