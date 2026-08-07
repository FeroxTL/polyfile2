def get_storage_path(storage_cls: type) -> str:
    return f"{storage_cls.__module__}.{storage_cls.__name__}"
