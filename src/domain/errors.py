from __future__ import annotations


class InvalidJobTransition(Exception):  # noqa: N818
    """Доменная ошибка: недопустимый переход машины состояний `CallProcessingJob`."""


__all__ = ["InvalidJobTransition"]
