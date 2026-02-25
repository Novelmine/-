from app import app
from db import init_db

# Ensure tables exist at process boot in server environments (e.g., Render)
init_db()

application = app
