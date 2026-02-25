import logging

from app import app
from db import init_db

logger = logging.getLogger(__name__)

try:
    # Best-effort schema bootstrap. App should still boot even if DB is temporarily unreachable.
    init_db()
except Exception as exc:
    logger.warning("init_db skipped during boot: %s", exc)

application = app
