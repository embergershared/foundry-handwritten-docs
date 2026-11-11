"""Network-free adapter doubles: no credentials, endpoints or document uploads."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from azure.core.exceptions import ServiceRequestError

from handwritten_docs.services import Authorization, DocumentIntelligence, FoundryVision


def grant() -> Authorization:
    return Authorization(
        source_sha256="a" * 64,
        endpoint="https://example.invalid",
        approved_pages=[1],
        target_reference="synthetic",
        data_permission_reference="synthetic",
    )


def test_di_checkpoint_resume_uses_same_operation(tmp_path: Path) -> None:
    failed = SimpleNamespace(
        result=AsyncMock(side_effect=ServiceRequestError("synthetic")),
        continuation_token=lambda: "synthetic-operation-token",
    )
    raw = {"apiVersion": "2024-11-30", "modelId": "prebuilt-layout"}
    done = SimpleNamespace(
        result=AsyncMock(return_value=SimpleNamespace(as_dict=lambda: raw)),
        continuation_token=lambda: "synthetic-operation-token",
    )
    client = SimpleNamespace(begin_analyze_document=AsyncMock(side_effect=[failed, done]))
    adapter = DocumentIntelligence(client, grant(), "https://example.invalid", "a" * 64, 1)
    checkpoint = tmp_path / "operation.json"
    with pytest.raises(ServiceRequestError):
        asyncio.run(adapter.recognize(b"synthetic-image", checkpoint))
    result = asyncio.run(adapter.recognize(b"synthetic-image", checkpoint))
    assert result["stringIndexType"] == "unicodeCodePoint"
    assert client.begin_analyze_document.call_args_list[1].kwargs["continuation_token"] == (
        "synthetic-operation-token"
    )
    assert client.begin_analyze_document.call_args_list[0].kwargs["string_index_type"] == (
        "unicodeCodePoint"
    )
    with pytest.raises(ValueError, match="another request"):
        asyncio.run(adapter.recognize(b"changed-image", checkpoint))


def test_ambiguous_di_post_never_silently_submitted_twice(tmp_path: Path) -> None:
    client = SimpleNamespace(
        begin_analyze_document=AsyncMock(side_effect=ServiceRequestError("synthetic"))
    )
    adapter = DocumentIntelligence(client, grant(), "https://example.invalid", "a" * 64, 1)
    checkpoint = tmp_path / "operation.json"
    with pytest.raises(ServiceRequestError):
        asyncio.run(adapter.recognize(b"synthetic-image", checkpoint))
    with pytest.raises(ValueError, match="outcome unknown"):
        asyncio.run(adapter.recognize(b"synthetic-image", checkpoint))
    assert client.begin_analyze_document.call_count == 1


@pytest.mark.parametrize("reason,refusal", [("length", None), ("stop", "refused")])
def test_vision_refusal_and_truncation_are_errors(reason: str, refusal: str | None) -> None:
    message = SimpleNamespace(refusal=refusal, parsed=None)
    completion = SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason, message=message)])
    parse = AsyncMock(return_value=completion)
    client = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )
    adapter = FoundryVision(
        client, grant(), "https://example.invalid", "a" * 64, 1, "synthetic-deployment"
    )
    with pytest.raises(ValueError, match="refused or truncated"):
        asyncio.run(adapter.recognize(b"synthetic", [("crop", b"crop")], {"units": "points"}))
    payload = parse.call_args.kwargs
    assert payload["messages"][1]["content"][2]["image_url"]["detail"] == "high"
    assert payload["temperature"] == 0
