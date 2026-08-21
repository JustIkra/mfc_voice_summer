import tomllib
from pathlib import Path

FINAL_REPOSITORY = Path("/Users/maksim/git_projects/mfc_voice_summer")


def test_project_config_registers_only_approved_otp_tool() -> None:
    worktree = Path(__file__).resolve().parents[3]
    config = tomllib.loads((worktree / ".codex" / "config.toml").read_text())
    server = config["mcp_servers"]["project_otp"]
    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "--locked",
        "--project",
        str(FINAL_REPOSITORY / ".codex" / "otp-mcp"),
        "otp-mcp",
        "serve",
    ]
    assert server["cwd"] == str(FINAL_REPOSITORY)
    assert server["enabled_tools"] == ["get_totp"]
    assert server["default_tools_approval_mode"] == "prompt"
    assert server["required"] is False
