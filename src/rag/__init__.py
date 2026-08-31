__all__ = ["load_gdpr_chunks", "retrieve", "StaleIndexError"]


def __getattr__(name: str):
    if name == "load_gdpr_chunks":
        from src.rag.chunker import load_gdpr_chunks

        return load_gdpr_chunks
    if name == "retrieve":
        from src.rag.retrieve import retrieve

        return retrieve
    if name == "StaleIndexError":
        from src.rag.retrieve import StaleIndexError

        return StaleIndexError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
