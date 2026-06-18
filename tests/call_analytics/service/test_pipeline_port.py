import pytest

from call_analytics.service.ports import CallProcessingPipeline


def test_pipeline_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        CallProcessingPipeline()  # type: ignore[abstract]
