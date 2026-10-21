"""Export the actual FastAPI contract, without starting storage or changing backend code."""

import json
from pathlib import Path

from app.main import app


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
    target.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OpenAPI exported to {target}")


if __name__ == "__main__":
    main()
