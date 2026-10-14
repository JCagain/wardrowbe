from unittest.mock import patch

import httpx
import pytest

from app.services.ai_service import AIResponseTruncatedError, AIService, ClothingTags

FAKE_REQUEST = httpx.Request("POST", "http://ai-endpoint.test/chat/completions")


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=FAKE_REQUEST)


class TestTagParsing:
    """Tests for AI response parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "blue",
            "colors": ["blue", "white"],
            "pattern": "striped",
            "material": "cotton",
            "formality": "casual",
            "confidence": 0.85
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.type == "shirt"
        assert tags.primary_colors == ["blue"]
        # a primary color is never repeated in the secondary list
        assert tags.secondary_colors == ["white"]
        assert tags.pattern == "striped"
        assert tags.material == "cotton"
        # Confidence is now computed by compute_tag_completeness (not AI self-reported)
        # type(0.25) + primary_colors(0.20) + pattern(0.15) + formality(0.15) + material(0.10) + secondary_colors(0.05) = 0.90
        assert tags.confidence == 0.9

    def test_parse_json_in_markdown(self):
        """Test parsing JSON wrapped in markdown code block."""
        service = AIService()
        response = """
        Here's the analysis:
        ```json
        {
            "type": "pants",
            "primary_color": "black",
            "colors": ["black"],
            "material": "denim",
            "confidence": 0.9
        }
        ```
        """
        tags = service._parse_tags_from_response(response)
        assert tags.type == "pants"
        assert tags.primary_colors == ["black"]
        assert tags.material == "denim"

    def test_parse_invalid_type(self):
        """Test that invalid type returns unknown."""
        service = AIService()
        response = """
        {
            "type": "invalid_type_xyz",
            "primary_color": "blue"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.type == "unknown"

    def test_rejected_type_is_kept_as_unrecognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": " Tights ", "primary_color": "black"}')
        assert tags.type == "unknown"
        assert tags.unrecognized_type == "tights"

    def test_missing_type_is_not_unrecognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"primary_color": "black"}')
        assert tags.type == "unknown"
        assert tags.unrecognized_type is None

    def test_valid_type_is_not_unrecognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": "socks"}')
        assert tags.unrecognized_type is None

    def test_parse_invalid_color(self):
        """Test that invalid colors are filtered out."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "chartreuse",
            "colors": ["blue", "invalid_color", "black"]
        }
        """
        tags = service._parse_tags_from_response(response)
        # Invalid colors should be removed
        # Invalid primary dropped -> valid secondaries are promoted (Ruling 59)
        assert tags.primary_colors == ["blue", "black"]
        assert tags.secondary_colors == []
        assert "invalid_color" not in tags.primary_colors

    def test_parse_grey_to_gray(self):
        """Test that 'grey' is normalized to 'gray'."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "grey"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.primary_colors == ["gray"]

    def test_parse_invalid_json(self):
        """Test parsing completely invalid response."""
        service = AIService()
        response = "This is not JSON at all, just some random text."
        tags = service._parse_tags_from_response(response)
        assert tags.type == "unknown"
        assert tags.raw_response == response

    def test_parse_confidence_computed_from_completeness(self):
        """Test that confidence is computed from tag completeness, not AI self-reported value."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "confidence": 1.5
        }
        """
        tags = service._parse_tags_from_response(response)
        # Confidence is now computed by compute_tag_completeness: type only = 0.25
        assert tags.confidence == 0.25

    def test_parse_valid_formality(self):
        """Test parsing formality levels."""
        service = AIService()
        response = """
        {
            "type": "blazer",
            "formality": "business-casual"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.formality == "business-casual"

    def test_parse_invalid_formality(self):
        """Test that invalid formality is None."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "formality": "ultra-super-formal"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.formality is None

    def test_parse_very_formal(self):
        service = AIService()
        response = '{"type": "suit", "formality": "very-formal", "material": "shearling"}'
        tags = service._parse_tags_from_response(response)
        assert tags.type == "suit"
        assert tags.formality == "very-formal"
        assert tags.material == "shearling"

    def test_parse_down_material(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": "jacket", "material": "down"}')
        assert tags.material == "down"


class TestClothingTags:
    """Tests for ClothingTags model."""

    def test_default_values(self):
        """Test default values for ClothingTags."""
        tags = ClothingTags()
        assert tags.type == "unknown"
        assert tags.primary_colors == []
        assert tags.secondary_colors == []
        assert tags.style == []
        assert tags.confidence == 0.0

    def test_full_construction(self):
        """Test constructing ClothingTags with all fields."""
        tags = ClothingTags(
            type="jacket",
            subtype="blazer",
            primary_colors=["navy"],
            secondary_colors=["white"],
            pattern="solid",
            material="wool",
            style=["formal", "classic"],
            formality="formal",
            season=["fall", "winter"],
            confidence=0.92,
            description="A classic navy blazer",
        )
        assert tags.type == "jacket"
        assert tags.subtype == "blazer"
        assert tags.primary_colors == ["navy"]
        assert tags.secondary_colors == ["white"]
        assert tags.confidence == 0.92


class TestGenerateTextTruncatedResponse:
    """Regression tests for issue #139: reasoning-capable models (e.g. Qwen3 via

    LM Studio) can exhaust the entire completion token budget on their
    ``reasoning_content`` chain-of-thought, leaving ``message.content`` empty with
    ``finish_reason == "length"``. That used to surface as an opaque "Could not parse
    AI response as JSON: " error, further masked upstream as a generic "AI service is
    not available" message. It should now raise AIResponseTruncatedError with the real
    cause, every retry attempt, so callers can tell the user what actually happened.
    """

    @staticmethod
    def _truncated_reasoning_response() -> dict:
        # Mirrors the exact shape reported in the issue's attached LM Studio /
        # backend logs: assistant content is empty, the model's chain-of-thought
        # landed in reasoning_content instead, and finish_reason is "length".
        return {
            "id": "chatcmpl-j0ue2a2xp0kziw0f8gof",
            "object": "chat.completion",
            "model": "qwen/qwen3.5-9b",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "The user wants me to create 3 outfits...",
                        "tool_calls": [],
                    },
                    "finish_reason": "length",
                }
            ],
            "usage": {"prompt_tokens": 3417, "completion_tokens": 4775, "total_tokens": 8192},
        }

    @pytest.mark.asyncio
    async def test_empty_content_with_reasoning_raises_truncated_error(self):
        service = AIService()
        mock_response = _mock_response(self._truncated_reasoning_response())

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(AIResponseTruncatedError) as exc_info:
                await service.generate_text("suggest an outfit")

        message = str(exc_info.value)
        assert "reasoning" in message
        assert "AI_MAX_TOKENS" in message

    @pytest.mark.asyncio
    async def test_empty_content_without_reasoning_still_raises_truncated_error(self):
        service = AIService()
        payload = self._truncated_reasoning_response()
        del payload["choices"][0]["message"]["reasoning_content"]
        mock_response = _mock_response(payload)

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(AIResponseTruncatedError):
                await service.generate_text("suggest an outfit")

    @pytest.mark.asyncio
    async def test_missing_content_key_raises_truncated_error(self):
        # Some providers omit the "content" key entirely instead of returning ""
        # when the response is truncated; bracket access would raise KeyError
        # instead of the actionable AIResponseTruncatedError.
        service = AIService()
        payload = self._truncated_reasoning_response()
        del payload["choices"][0]["message"]["content"]
        mock_response = _mock_response(payload)

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(AIResponseTruncatedError):
                await service.generate_text("suggest an outfit")

    @pytest.mark.asyncio
    async def test_normal_response_is_unaffected(self):
        service = AIService()
        payload = self._truncated_reasoning_response()
        payload["choices"][0]["message"]["content"] = '{"outfits": []}'
        payload["choices"][0]["message"]["reasoning_content"] = ""
        payload["choices"][0]["finish_reason"] = "stop"
        mock_response = _mock_response(payload)

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'


class TestGenerateTextErrorEnvelope:
    """HTTP 200 provider error envelopes must use normal retry/fallback handling."""

    @staticmethod
    def _success_response() -> httpx.Response:
        return _mock_response(
            {
                "model": "text-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            }
        )

    @pytest.mark.asyncio
    async def test_generate_text_retries_after_200_error_envelope(self):
        service = AIService()
        error_envelope = _mock_response({"error": {"message": "The operation was aborted"}})

        with patch(
            "httpx.AsyncClient.post", side_effect=[error_envelope, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == "ok"
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_text_repeated_200_error_envelope_raises_controlled_error(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        error_envelope = _mock_response({"error": {"message": "The operation was aborted"}})

        with patch("httpx.AsyncClient.post", return_value=error_envelope):
            with pytest.raises(RuntimeError, match="The operation was aborted"):
                await service.generate_text("suggest an outfit")


class TestLogprobsRejection:
    """Regression tests for issue #143: providers like Gemini reject the

    logprobs/top_logprobs request params with a 400, which used to burn every
    retry attempt and leave tags empty (while the separate, logprobs-free
    description call succeeded silently, giving no indication of the failure).
    """

    _TAGS_CONTENT = '{"type": "shirt", "primary_color": "blue", "colors": ["blue"]}'

    @staticmethod
    def _logprobs_rejected_response() -> httpx.Response:
        # Mirrors Gemini's OpenAI-compat error shape from the issue report.
        return _mock_response(
            {"error": {"message": 'Unknown name "logprobs": Cannot find field.'}},
            status_code=400,
        )

    @staticmethod
    def _success_response(content: str) -> httpx.Response:
        return _mock_response(
            {
                "model": "gemini-2.0-flash",
                "choices": [{"message": {"content": content}}],
            }
        )

    @pytest.mark.asyncio
    async def test_retries_without_logprobs_after_rejection(self):
        service = AIService()
        responses = [self._logprobs_rejected_response(), self._success_response(self._TAGS_CONTENT)]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert logprobs_content is None
        assert mock_post.call_count == 2
        first_body = mock_post.call_args_list[0].kwargs["json"]
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert first_body["logprobs"] is True
        assert "logprobs" not in second_body
        assert "top_logprobs" not in second_body

    @pytest.mark.asyncio
    async def test_retries_without_logprobs_after_200_error_envelope(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        error_envelope = _mock_response(
            {"error": {"message": 'Unknown name "logprobs": Cannot find field.'}}
        )
        responses = [error_envelope, self._success_response(self._TAGS_CONTENT)]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert logprobs_content is None
        assert mock_post.call_count == 2
        first_body = mock_post.call_args_list[0].kwargs["json"]
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert first_body["logprobs"] is True
        assert "logprobs" not in second_body
        assert "top_logprobs" not in second_body

    @pytest.mark.asyncio
    async def test_repeated_200_error_envelope_returns_controlled_error(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        error_envelope = _mock_response({"error": {"message": "The operation was aborted"}})

        with patch("httpx.AsyncClient.post", return_value=error_envelope) as mock_post:
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert content is None
        assert isinstance(err, RuntimeError)
        assert "The operation was aborted" in str(err)
        assert logprobs_content is None
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_transient_200_error_envelope_keeps_logprobs_and_backs_off(self):
        # An overloaded provider says nothing about logprobs, so dropping them would cost
        # the item its logprobs confidence and hammer the endpoint with no backoff.
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 2})
        error_envelope = _mock_response({"error": {"message": "Model is overloaded"}})
        logprobs = [{"token": "shirt", "logprob": -0.1}]
        success = _mock_response(
            {
                "model": "gemini-2.0-flash",
                "choices": [
                    {"message": {"content": self._TAGS_CONTENT}, "logprobs": {"content": logprobs}}
                ],
            }
        )

        with (
            patch("httpx.AsyncClient.post", side_effect=[error_envelope, success]) as mock_post,
            patch("app.services.ai_service.asyncio.sleep") as mock_sleep,
        ):
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert logprobs_content == logprobs
        assert mock_post.call_args_list[1].kwargs["json"]["logprobs"] is True
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logprobs_rejection_does_not_consume_retry_budget(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        responses = [self._logprobs_rejected_response(), self._success_response(self._TAGS_CONTENT)]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content, err, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_unrelated_400_is_not_treated_as_logprobs_rejection(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        unrelated_400 = _mock_response({"error": {"message": "invalid model"}}, status_code=400)

        with patch("httpx.AsyncClient.post", return_value=unrelated_400) as mock_post:
            content, err, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert content is None
        assert err is not None
        assert mock_post.call_count == 1


class TestReasoningEffort:
    """Tests for reasoning_effort configuration, rejection handling, and recovery."""

    @staticmethod
    def _reasoning_effort_rejected_response() -> httpx.Response:
        return _mock_response(
            {
                "error": {
                    "message": "Unsupported parameter: 'reasoning_effort' is not supported with this model."
                }
            },
            status_code=400,
        )

    @staticmethod
    def _success_response(content: str = '{"outfits": []}') -> httpx.Response:
        return _mock_response(
            {
                "model": "gemma4:12b",
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            }
        )

    @pytest.mark.asyncio
    async def test_generate_text_includes_default_reasoning_effort(self):
        service = AIService()
        mock_response = self._success_response()

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            await service.generate_text("suggest an outfit")

        assert mock_post.call_count == 1
        body = mock_post.call_args.kwargs["json"]
        assert body.get("reasoning_effort") == "none"

    @pytest.mark.asyncio
    async def test_generate_text_retries_without_reasoning_effort_after_rejection(self):
        service = AIService()
        responses = [self._reasoning_effort_rejected_response(), self._success_response()]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert mock_post.call_count == 2
        first_body = mock_post.call_args_list[0].kwargs["json"]
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert first_body.get("reasoning_effort") == "none"
        assert "reasoning_effort" not in second_body

    @pytest.mark.asyncio
    async def test_generate_text_retries_without_reasoning_effort_after_200_error_envelope(self):
        service = AIService()
        rejected = _mock_response(
            {"error": {"message": "Unsupported parameter: 'reasoning_effort'"}}
        )
        with patch(
            "httpx.AsyncClient.post", side_effect=[rejected, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert "reasoning_effort" not in mock_post.call_args_list[1].kwargs["json"]

    @pytest.mark.asyncio
    async def test_vision_retries_without_reasoning_effort_after_200_error_envelope(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        rejected = _mock_response(
            {"error": {"message": "Unsupported parameter: 'reasoning_effort'"}}
        )
        with patch(
            "httpx.AsyncClient.post", side_effect=[rejected, self._success_response("tags")]
        ) as mock_post:
            content, err, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags"
            )

        assert err is None
        assert content == "tags"
        assert "reasoning_effort" not in mock_post.call_args_list[1].kwargs["json"]

    @pytest.mark.asyncio
    async def test_empty_content_with_ollama_reasoning_raises_truncated_error(self):
        service = AIService()
        # Ollama returns "reasoning", not "reasoning_content"
        ollama_response = _mock_response(
            {
                "id": "chatcmpl-123",
                "model": "gemma4:12b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning": "Let me think about styling outfits...",
                        },
                        "finish_reason": "length",
                    }
                ],
            }
        )

        with patch("httpx.AsyncClient.post", return_value=ollama_response):
            with pytest.raises(AIResponseTruncatedError) as exc_info:
                await service.generate_text("suggest an outfit")

        assert "reasoning" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_truncation_recovers_by_retrying_with_none(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_reasoning_effort": "high"})
        truncated = _mock_response(
            {
                "id": "chatcmpl-123",
                "model": "gemma4:12b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning": "Thinking consumed all tokens...",
                        },
                        "finish_reason": "length",
                    }
                ],
            }
        )
        success = self._success_response('{"outfits": [{"items": [1, 2]}]}')

        with patch("httpx.AsyncClient.post", side_effect=[truncated, success]) as mock_post:
            result = await service.generate_text("suggest an outfit")

        assert "items" in result
        assert mock_post.call_count == 2
        # First call had reasoning_effort="high"
        assert mock_post.call_args_list[0].kwargs["json"].get("reasoning_effort") == "high"
        # Recovered call switched to reasoning_effort="none"
        assert mock_post.call_args_list[1].kwargs["json"].get("reasoning_effort") == "none"

    @pytest.mark.asyncio
    async def test_ollama_invalid_think_value_falls_back_without_reasoning_effort(self):
        # Ollama releases predating the "none" effort level reject it without ever naming
        # reasoning_effort, so matching only OpenAI's wording would fail every request.
        service = AIService()
        ollama_rejection = _mock_response(
            {
                "error": 'invalid think value: "none" (must be "high", "medium", "low", true, or false)'
            },
            status_code=400,
        )

        with patch(
            "httpx.AsyncClient.post", side_effect=[ollama_rejection, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0].kwargs["json"].get("reasoning_effort") == "none"
        assert "reasoning_effort" not in mock_post.call_args_list[1].kwargs["json"]

    @pytest.mark.asyncio
    async def test_transient_empty_response_still_retries(self):
        service = AIService()
        empty = _mock_response(
            {
                "model": "gemma3:latest",
                "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            }
        )

        with patch(
            "httpx.AsyncClient.post", side_effect=[empty, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_length_cutoff_at_lowest_effort_does_not_retry(self):
        service = AIService()
        truncated = _mock_response(
            {
                "model": "gemma4:12b",
                "choices": [
                    {
                        "message": {"content": "", "reasoning": "still thinking"},
                        "finish_reason": "length",
                    }
                ],
            }
        )

        with patch("httpx.AsyncClient.post", return_value=truncated) as mock_post:
            with pytest.raises(AIResponseTruncatedError):
                await service.generate_text("suggest an outfit")

        assert mock_post.call_count == 1


class TestColorAliases:
    """AI/legacy colors map through the alias table first, then drop what the
    vocabulary does not contain — unknown values never reach the columns."""

    def test_colors_list_maps_aliases_and_drops_unknown(self):
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "burgundy",
            "colors": ["burgundy", "sky blue", "navy", "glitter"]
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.primary_colors == ["wine"]
        assert tags.secondary_colors == ["sky", "navy"]

    def test_primary_color_alias_is_mapped_not_dropped(self):
        service = AIService()
        response = '{"type": "shirt", "primary_color": "army-green", "colors": ["dark-brown"]}'
        tags = service._parse_tags_from_response(response)
        assert tags.primary_colors == ["army"]
        assert tags.secondary_colors == ["coffee"]


@pytest.fixture
def service():
    return AIService()


class TestClosedSetColorContract:
    def test_parses_primary_and_secondary_color_arrays(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":["black","white"],"secondary_colors":["wine"]}'
        )
        assert tags.primary_colors == ["black", "white"]
        assert tags.secondary_colors == ["wine"]

    def test_slug_equals_label_echo_is_accepted(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":["black=黑"],"style":[" casual=休闲 "],"season":["all-season=四季"]}'
        )
        assert tags.primary_colors == ["black"]
        assert tags.season == ["all-season"]

    def test_a_primary_color_is_not_repeated_as_secondary(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":["black","black"],"secondary_colors":["black","white"]}'
        )
        assert tags.primary_colors == ["black"]
        assert tags.secondary_colors == ["white"]

    def test_secondary_only_is_promoted_to_primary(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":[],"secondary_colors":["black","white"]}'
        )
        assert tags.primary_colors == ["black", "white"]
        assert tags.secondary_colors == []

    def test_secondary_only_without_primary_key_is_promoted(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","secondary_colors":["black","white"]}'
        )
        assert tags.primary_colors == ["black", "white"]
        assert tags.secondary_colors == []

    def test_both_empty_stays_empty_and_warns(self, service, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            tags = service._parse_tags_from_response(
                '{"type":"shirt","primary_colors":[],"secondary_colors":[]}'
            )
        assert tags.primary_colors == []
        assert tags.secondary_colors == []
        assert any("no primary color" in r.getMessage().lower() for r in caplog.records)

    def test_unknown_colors_are_dropped_not_written(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":["chartreuse"],"secondary_colors":["neon"]}'
        )
        assert tags.primary_colors == []
        assert tags.secondary_colors == []

    def test_legacy_single_color_keys_still_parse(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_color":"burgundy","colors":["burgundy","sky blue"]}'
        )
        assert tags.primary_colors == ["wine"]
        assert tags.secondary_colors == ["sky"]

    def test_disabled_values_are_rejected_from_ai_output(self, service, vocab_file):
        import json

        data = json.loads(vocab_file.read_text())
        for c in data["colors"]["values"]:
            if c["value"] == "black":
                c["disabled"] = True
        vocab_file.write_text(json.dumps(data, ensure_ascii=False))
        import os

        os.utime(vocab_file, ns=(10**18, 10**18))  # force the mtime-keyed cache to reload
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":["black","white"]}'
        )
        assert tags.primary_colors == ["white"]

    def test_chinese_label_only_answers_map_to_slugs(self, service, vocab_file):
        import json

        data = json.loads(vocab_file.read_text())
        style = next(s for s in data["styles"] if not s.get("disabled"))
        tags = service._parse_tags_from_response(
            json.dumps(
                {
                    "type": "shirt",
                    "primary_colors": ["黑"],
                    "secondary_colors": ["克莱因蓝"],
                    "style": [style["label"]],
                    "season": ["春"],
                },
                ensure_ascii=False,
            )
        )
        assert tags.primary_colors == ["black"]
        assert tags.secondary_colors == ["klein"]
        assert tags.style == [style["value"]]
        assert tags.season == ["spring"]

    def test_disabled_entry_label_is_not_mapped(self, service, vocab_file):
        import json
        import os

        data = json.loads(vocab_file.read_text())
        for c in data["colors"]["values"]:
            if c["value"] == "black":
                c["disabled"] = True
        vocab_file.write_text(json.dumps(data, ensure_ascii=False))
        os.utime(vocab_file, ns=(10**18 + 5, 10**18 + 5))
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":["黑","白"]}'
        )
        assert tags.primary_colors == ["white"]

    def test_chinese_label_maps_type_too(self, service):
        tags = service._parse_tags_from_response('{"type":"衬衫"}')
        assert tags.type == "shirt"

    def test_empty_primary_with_secondary_promotes_and_logs_info(self, service, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            tags = service._parse_tags_from_response(
                '{"type":"shirt","primary_colors":[],"secondary_colors":["white"]}'
            )
        assert tags.primary_colors == ["white"]
        assert tags.secondary_colors == []
        assert any("promoted" in r.getMessage() and r.levelno == logging.INFO for r in caplog.records)

    @pytest.mark.parametrize("bad", ["5", "true", "null", '{"a":1}', '[1,null,{"x":2}]'])
    def test_malformed_color_values_do_not_crash(self, service, bad):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":%s,"secondary_colors":%s,"style":%s,"season":%s}'
            % (bad, bad, bad, bad)
        )
        assert tags.primary_colors == []
        assert tags.secondary_colors == []
        assert tags.style == []
        assert tags.season == []

    def test_bare_string_is_a_one_element_list(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":"black","secondary_colors":"white","style":"casual","season":"summer"}'
        )
        assert tags.primary_colors == ["black"]
        assert tags.secondary_colors == ["white"]
        assert tags.style == ["casual"]
        assert tags.season == ["summer"]

    def test_legacy_primary_fills_in_when_new_primary_is_null(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","primary_colors":null,"primary_color":"black"}'
        )
        assert tags.primary_colors == ["black"]

    def test_mixed_new_secondary_with_legacy_primary(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","secondary_colors":["white"],"primary_color":"black"}'
        )
        assert tags.primary_colors == ["black"]
        assert tags.secondary_colors == ["white"]

    def test_style_and_season_are_deduped(self, service):
        tags = service._parse_tags_from_response(
            '{"type":"shirt","style":["casual","casual"],"season":["summer","summer"]}'
        )
        assert tags.style == ["casual"]
        assert tags.season == ["summer"]

    def test_logprobs_confidence_counts_primary_colors_array(self):
        from app.services.ai_service import compute_confidence_from_logprobs

        def t(token, lp=-0.1):
            return {"token": token, "logprob": lp}

        only_colors = [t('"primary_colors"'), t(":"), t("["), t('"black"', -0.5), t("]")]
        got = compute_confidence_from_logprobs(only_colors)
        assert got is not None
        assert abs(got - 0.6065) < 0.01  # exp(-0.5)
