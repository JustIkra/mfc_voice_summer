from __future__ import annotations


class InvalidJobTransition(Exception):
    """Доменная ошибка: недопустимый переход машины состояний `CallProcessingJob`."""


__all__ = ["InvalidJobTransition"]
