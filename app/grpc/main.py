from app.core.config import get_settings
from app.core.logging import configure_logging
from app.grpc.server import serve


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    serve(settings)


if __name__ == "__main__":
    main()
