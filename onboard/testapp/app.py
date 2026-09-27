"""Tiny "shop" API used as a second, differently-built onboarding target (nginx -> gunicorn -> Flask -> SQLite; config read from git-tracked JSON)."""
import json
import logging
import os
import sqlite3
import time

from flask import Flask, jsonify, request

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config", "app.json")
DB = os.path.join(BASE, "shop.db")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
log = logging.getLogger("shop")
app = Flask(__name__)


def cfg() -> dict:
    with open(CFG, encoding="utf8") as f:
        return json.load(f)


def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=cfg().get("db_timeout_ms", 2000) / 1000)
    c.execute("create table if not exists orders(id integer primary key, item text, qty integer)")
    return c


@app.get("/")
def home():
    time.sleep(cfg().get("slow_ms", 0) / 1000)  # emulates a slow dependency / expensive query
    n = db().execute("select count(*) from orders").fetchone()[0]
    return jsonify(status="ok", orders=n)


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    c = db()
    c.execute("insert into orders(item, qty) values (?, ?)", (body.get("item", "widget"), int(body.get("qty", 1))))
    c.commit()
    log.info("order created item=%s", body.get("item", "widget"))
    return jsonify(ok=True), 201


@app.get("/health")
def health():
    return jsonify(ok=True)
