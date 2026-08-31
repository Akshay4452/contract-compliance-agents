__all__ = ["load_gdpr_chunks"]


def __getattr__(name: str):
    if name == "load_gdpr_chunks":
        from src.rag.chunker import load_gdpr_chunks

        return load_gdpr_chunks
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
