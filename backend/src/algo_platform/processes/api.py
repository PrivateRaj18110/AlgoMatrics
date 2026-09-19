import uvicorn

from algo_platform.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "algo_platform.api.app:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxy_ips,
    )


if __name__ == "__main__":
    main()
