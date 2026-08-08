# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from js8link.js8call import JS8CallClient


@pytest.mark.asyncio
async def test_request_correlates_response_and_receives_events() -> None:
    events: list[dict] = []
    messages: list[tuple[str, bool]] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await reader.readline())
        request_id = request["params"]["_ID"]
        event = json.dumps({"type": "RX.ACTIVITY", "params": {}, "value": "CQ"}).encode() + b"\n"
        response = (
            json.dumps(
                {"type": "STATION.VERSION", "params": {"_ID": request_id, "VERSION": "3.0.0"}, "value": ""}
            ).encode()
            + b"\n"
        )
        # TCP may split one JSON envelope over multiple reads.  The client
        # must wait for the newline delimiter instead of treating fragments as
        # malformed JSON.
        writer.write(event[:9])
        await writer.drain()
        await asyncio.sleep(0.01)
        writer.write(event[9:] + response[:13])
        await writer.drain()
        await asyncio.sleep(0.01)
        writer.write(response[13:])
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def on_event(message: dict) -> None:
        events.append(message)

    async def on_message(message: dict, is_response: bool) -> None:
        messages.append((message["type"], is_response))

    client = JS8CallClient("127.0.0.1", port, on_event, on_message)
    response = await client.connect()
    await asyncio.sleep(0.05)
    assert response["params"]["VERSION"] == "3.0.0"
    assert events[0]["type"] == "RX.ACTIVITY"
    assert messages == [("RX.ACTIVITY", False), ("STATION.VERSION", True)]
    await client.close()
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_malformed_json_and_structural_messages_do_not_stop_read_loop() -> None:
    malformed: list[bytes] = []
    events: list[dict] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await reader.readline())
        request_id = request["params"]["_ID"]
        writer.write(
            json.dumps(
                {"type": "STATION.VERSION", "params": {"_ID": request_id, "VERSION": "3.0.0"}, "value": ""}
            ).encode()
            + b"\n"
        )
        writer.write(b"{not-json}\n")
        writer.write(b"[\"not an API envelope\"]\n")
        writer.write(b'{"type":"RX.ACTIVITY","params":{"_ID":"invalid"},"value":"CQ"}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def on_event(message: dict) -> None:
        events.append(message)

    async def on_malformed(raw: bytes) -> None:
        malformed.append(raw)

    client = JS8CallClient("127.0.0.1", port, on_event=on_event, on_malformed=on_malformed)
    await client.connect()
    await asyncio.sleep(0.1)

    assert malformed == [b"{not-json}", b'["not an API envelope"]']
    assert events == [{"type": "RX.ACTIVITY", "params": {"_ID": "invalid"}, "value": "CQ"}]
    await client.close()
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_request_timeout_removes_pending_request(monkeypatch) -> None:
    client = JS8CallClient("127.0.0.1", 2442)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer

    async def timeout(awaitable, _seconds=None, **_kwargs):
        awaitable.cancel()
        raise TimeoutError

    monkeypatch.setattr("js8link.js8call.asyncio.wait_for", timeout)

    with pytest.raises(asyncio.TimeoutError):
        await client.request("PING")

    assert client._pending == {}


@pytest.mark.asyncio
async def test_concurrent_requests_have_unique_ids() -> None:
    request_ids: list[int] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await reader.readline())
        writer.write(
            json.dumps(
                {
                    "type": "STATION.VERSION",
                    "params": {"_ID": request["params"]["_ID"], "VERSION": "3.0.0"},
                    "value": "",
                }
            ).encode()
            + b"\n"
        )
        await writer.drain()
        for _ in range(3):
            request = json.loads(await reader.readline())
            request_ids.append(request["params"]["_ID"])
            writer.write(
                json.dumps({"type": "PONG", "params": {"_ID": request["params"]["_ID"]}, "value": ""}).encode() + b"\n"
            )
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = JS8CallClient("127.0.0.1", port)
    await client.connect()
    responses = await asyncio.gather(client.request("PING"), client.request("PING"), client.request("PING"))
    assert all(response["type"] == "PONG" for response in responses)
    assert len(request_ids) == len(set(request_ids)) == 3
    await client.close()
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_outbound_callback_receives_requests_and_commands() -> None:
    outbound: list[tuple[dict, bool]] = []

    async def on_outbound(payload: dict, expects_response: bool) -> None:
        outbound.append((payload, expects_response))

    client = JS8CallClient("127.0.0.1", 2442, on_outbound=on_outbound)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer
    await client.send("TX.SEND_MESSAGE", "HELLO")
    assert outbound[0][0]["type"] == "TX.SEND_MESSAGE"
    assert outbound[0][1] is False
    writer.write.assert_called_once()
