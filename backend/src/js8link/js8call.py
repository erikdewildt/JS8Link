# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from itertools import count
from typing import Any


class JS8CallError(RuntimeError):
    pass


EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
MessageHandler = Callable[[dict[str, Any], bool], Awaitable[None]]
OutboundHandler = Callable[[dict[str, Any], bool], Awaitable[None]]
MalformedMessageHandler = Callable[[bytes], Awaitable[None]]
logger = logging.getLogger(__name__)


class JS8CallClient:
    def __init__(
        self,
        host: str,
        port: int,
        on_event: EventHandler | None = None,
        on_message: MessageHandler | None = None,
        on_outbound: OutboundHandler | None = None,
        on_malformed: MalformedMessageHandler | None = None,
    ) -> None:
        self.host, self.port, self.on_event, self.on_message = host, port, on_event, on_message
        self.on_outbound = on_outbound
        self.on_malformed = on_malformed
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._request_ids = count(int(time.time() * 1000))
        self.version: str | None = None

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    @property
    def version_tuple(self) -> tuple[int, ...]:
        if not self.version:
            return (0,)
        try:
            return tuple(int(part) for part in self.version.split("."))
        except (ValueError, TypeError):
            return (0,)

    async def connect(self) -> dict[str, Any]:
        if self.connected:
            return await self.request("STATION.VERSION")
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=8)
        self._reader_task = asyncio.create_task(self._read_loop())
        version_response = await self.request("STATION.VERSION")
        self.version = (version_response.get("params") or {}).get("VERSION") or None
        return version_response

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.reader = self.writer = None

    async def request(self, message_type: str, value: str = "", params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.writer or self.writer.is_closing():
            raise JS8CallError("JS8Call is not connected")
        request_id = next(self._request_ids)
        payload = {"type": message_type, "value": value, "params": {**(params or {}), "_ID": request_id}}
        if self.on_outbound:
            try:
                await self.on_outbound(payload, True)
            except Exception:
                # Diagnostics must never prevent radio control from continuing.
                logger.exception("Failed to record outgoing JS8Call API request")
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        async with self._lock:
            self._pending[request_id] = future
            self.writer.write((json.dumps(payload) + "\n").encode())
            await self.writer.drain()
        try:
            return await asyncio.wait_for(future, timeout=8)
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

    async def send(self, message_type: str, value: str = "", params: dict[str, Any] | None = None) -> None:
        """Send a command that JS8Call acknowledges through an asynchronous event."""
        if not self.writer or self.writer.is_closing():
            raise JS8CallError("JS8Call is not connected")
        payload = {"type": message_type, "value": value, "params": {**(params or {}), "_ID": -1}}
        if self.on_outbound:
            try:
                await self.on_outbound(payload, False)
            except Exception:
                # Diagnostics must never prevent radio control from continuing.
                logger.exception("Failed to record outgoing JS8Call API command")
        async with self._lock:
            self.writer.write((json.dumps(payload) + "\n").encode())
            await self.writer.drain()

    async def _read_loop(self) -> None:
        assert self.reader is not None
        try:
            while line := await self.reader.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    if self.on_malformed:
                        try:
                            await self.on_malformed(line.rstrip(b"\r\n"))
                        except Exception:
                            logger.exception("Failed to diagnose malformed JS8Call API message")
                    continue
                if not isinstance(message, dict):
                    if self.on_malformed:
                        try:
                            await self.on_malformed(line.rstrip(b"\r\n"))
                        except Exception:
                            logger.exception("Failed to diagnose malformed JS8Call API message")
                    continue
                params = message.get("params") or {}
                if not isinstance(params, dict):
                    if self.on_malformed:
                        try:
                            await self.on_malformed(line.rstrip(b"\r\n"))
                        except Exception:
                            logger.exception("Failed to diagnose malformed JS8Call API message")
                    continue
                request_id = params.get("_ID")
                future: asyncio.Future[dict[str, Any]] | None = None
                is_response = False
                async with self._lock:
                    if request_id is not None:
                        try:
                            future = self._pending.get(int(request_id))
                        except (TypeError, ValueError):
                            # Keep malformed correlation IDs out of the pending
                            # request map, but still allow the envelope to be
                            # diagnosed and delivered as an unsolicited event.
                            future = None
                    is_response = future is not None
                if future and not future.done():
                    try:
                        future.set_result(message)
                    except asyncio.InvalidStateError:
                        pass  # request() already timed out and cancelled the future
                if self.on_message:
                    try:
                        await self.on_message(message, is_response)
                    except Exception:
                        logger.exception("Failed to persist JS8Call API message")
                if not is_response and self.on_event:
                    try:
                        await self.on_event(message)
                    except Exception:
                        logger.exception("Failed to process JS8Call event")
        except (asyncio.CancelledError, ConnectionError):
            pass
        finally:
            self.writer = None
            async with self._lock:
                for pending_future in self._pending.values():
                    if not pending_future.done():
                        pending_future.set_exception(JS8CallError("JS8Call connection closed"))
                self._pending.clear()
