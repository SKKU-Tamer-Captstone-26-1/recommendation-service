import logging

from app.core.config import get_settings
from app.grpc.server import serve


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    serve(settings)


if __name__ == "__main__":
    main()
