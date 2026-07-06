import io
import os
from datetime import date

import pytest
from openpyxl import Workbook

# Safety net: never touch a real gantt.db during tests (set BEFORE loading .env,
# so this :memory: override wins over the .env DATABASE_URL).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Load .env so the live gate's skipif (which reads OPENROUTER_API_KEY at import
# time) sees the key. Real env still wins over the file.
from app.deps import load_dotenv  # noqa: E402

load_dotenv()

# Fixed project start so scheduled dates are deterministic in assertions.
FIXED_START = date(2026, 1, 1)


@pytest.fixture
def start() -> date:
    return FIXED_START


def make_xlsx(headers: list, rows: list[list]) -> bytes:
    """Build an in-memory .xlsx with the given header row + data rows."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
