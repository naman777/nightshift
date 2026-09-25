"""Slack Bolt app (Socket Mode): approval buttons and a status slash command, relayed to the gateway.

  pip install -e ".[slack]"
  SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-... python -m slackbot.bolt_app

Alternative without Socket Mode: point your Slack app's Interactivity Request URL at the gateway's POST /slack/interactive
(it verifies the signing secret), which does the same thing over plain HTTP.
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8000")


async def _post(path: str, body: dict) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        (await c.post(f"{GATEWAY}{path}", json=body)).raise_for_status()


def build_app():
    from slack_bolt.async_app import AsyncApp

    app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])

    @app.action("nightshift_approve")
    async def approve(ack, body, respond):
        await ack()
        iid = json.loads(body["actions"][0]["value"])["incident_id"]
        user = body["user"].get("username", "slack-user")
        await _post(f"/incidents/{iid}/approve", {"user": user})
        await respond(f":white_check_mark: {iid} approved by <@{body['user']['id']}>; executing.")

    @app.action("nightshift_reject")
    async def reject(ack, body, respond):
        await ack()
        iid = json.loads(body["actions"][0]["value"])["incident_id"]
        await _post(f"/incidents/{iid}/reject", {"user": body["user"].get("username", "slack-user")})
        await respond(f":no_entry: {iid} rejected by <@{body['user']['id']}>.")

    @app.command("/nightshift")
    async def status(ack, command, respond):
        await ack()
        iid = command["text"].strip()
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{GATEWAY}/incidents/{iid}" if iid else f"{GATEWAY}/incidents")
        await respond(f"```{r.text[:2800]}```")

    return app


async def main() -> None:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    await AsyncSocketModeHandler(build_app(), os.environ["SLACK_APP_TOKEN"]).start_async()


if __name__ == "__main__":
    asyncio.run(main())
