"""The start/stop/restart CLI verbs delegate to deploy/compendiumctl."""

from __future__ import annotations

import subprocess

import pytest

from compendium.__main__ import main


@pytest.mark.parametrize("verb", ["start", "stop", "restart"])
def test_stack_verbs_invoke_compendiumctl(monkeypatch, verb):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert main([verb]) == 0
    assert len(calls) == 1
    assert calls[0][0].endswith("deploy/compendiumctl")
    assert calls[0][1] == verb


def test_stack_verb_propagates_exit_code(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: subprocess.CompletedProcess(args, returncode=3),
    )
    assert main(["stop"]) == 3
