def api_docs_urls(
    environment: str,
    enabled: bool,
) -> tuple[str | None, str | None, str | None]:
    if environment != "development" or not enabled:
        return None, None, None
    return "/docs", "/redoc", "/openapi.json"
