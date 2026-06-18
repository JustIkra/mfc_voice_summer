import pytest

from call_analytics.infra.ports import ArtifactStore, JobRepository


@pytest.mark.parametrize("port", [JobRepository, ArtifactStore])
def test_persistence_ports_are_abstract(port: type) -> None:
    with pytest.raises(TypeError):
        port()  # type: ignore[abstract]
