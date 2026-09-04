from flask import request


def paginate(query, serializer, postprocess=None):
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError):
        page_size = 20

    total = query.count()

    items = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    if postprocess:
        postprocess(items)

    return {
        "items": [serializer(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
