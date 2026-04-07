"""
Custom LLM client for Graphiti + Ollama

Goals:
- Work with Graphiti's structured outputs using local (or cloud) Ollama models
- Simplify Pydantic JSON schemas for Ollama
- Robustly parse JSON (including markdown code blocks)
- Be compatible with DeepSeek, Qwen, Llama, etc. via Ollama's OpenAI API
- Make sampling as deterministic as possible (temperature=0, top_p=1, seed=0, etc.)
- Solution adapted from: https://github.com/getzep/graphiti/issues/868#issuecomment-3439031329
"""

import json
import re
from typing import Any, Type

from loguru import logger
from pydantic import BaseModel

from graphiti_core.llm_client.openai_generic_client import (
    OpenAIGenericClient,
    DEFAULT_MODEL,
)
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.client import get_extraction_language_instruction
from graphiti_core.prompts.models import Message


class OllamaGraphitiClient(OpenAIGenericClient):
    """
    LLM client optimized for using Ollama with Graphiti.

    Key ideas:
    - Instead of using OpenAI-style JSON schemas in the API call,
      we inject a simplified schema + EXAMPLE directly into the prompt.
    - We then parse the JSON manually and validate it with Pydantic.
    - If the model returns a schema instead of data, we fall back to
      an "empty but valid" structure so Graphiti doesn’t crash.
    - We call the OpenAI-compatible `chat.completions.create` directly
      so we can control temperature, top_p, penalties, seed, etc.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        logger.info(f"🦙 OllamaGraphitiClient initialized: {config.model}")

    # -------------------------------------------------------------------------
    # Helpers: example / empty structures from schema
    # -------------------------------------------------------------------------

    def _create_example_from_schema(self, schema: dict) -> dict:
        """
        Create an example JSON instance from a simplified JSON schema.
        This is used in the prompt to show the model what the OUTPUT
        should look like (not the schema itself).
        """
        if not isinstance(schema, dict):
            return {}

        properties = schema.get("properties", {})
        example: dict[str, Any] = {}

        for key, value_schema in properties.items():
            if not isinstance(value_schema, dict):
                continue

            value_type = value_schema.get("type", "string")

            if value_type == "array":
                items_schema = value_schema.get("items", {})
                if isinstance(items_schema, dict):
                    example[key] = [self._create_example_from_schema(items_schema)]
                else:
                    example[key] = []
            elif value_type == "object":
                example[key] = self._create_example_from_schema(value_schema)
            elif value_type == "string":
                example[key] = f"example_{key}"
            elif value_type == "integer":
                example[key] = 0
            elif value_type == "number":
                example[key] = 0.0
            elif value_type == "boolean":
                example[key] = False
            else:
                example[key] = None

        return example

    def _create_empty_from_schema(self, schema: dict) -> dict:
        """
        Create an *empty but valid* structure from a simplified schema.

        This is used as a fallback when the model returns a schema
        instead of data, or returns something that fails Pydantic validation.

        - arrays  -> []
        - objects -> recurse and fill properties with minimal values
        - string  -> ""
        - number  -> 0
        - integer -> 0
        - boolean -> False
        """
        if not isinstance(schema, dict):
            return {}

        properties = schema.get("properties", {})
        empty: dict[str, Any] = {}

        for key, value_schema in properties.items():
            if not isinstance(value_schema, dict):
                empty[key] = None
                continue

            value_type = value_schema.get("type", "string")

            if value_type == "array":
                empty[key] = []
            elif value_type == "object":
                empty[key] = self._create_empty_from_schema(value_schema)
            elif value_type == "string":
                empty[key] = ""
            elif value_type in ("integer", "number"):
                empty[key] = 0
            elif value_type == "boolean":
                empty[key] = False
            else:
                empty[key] = None

        return empty

    @staticmethod
    def _quote_relation_types(raw: str) -> str:
        """Quote unquoted SCREAMING_SNAKE_CASE relation_type values.

        Models sometimes emit `"relation_type": SOME_EDGE` without quotes, which
        breaks JSON parsing. This regex wraps those bare tokens in quotes while
        leaving already-quoted values untouched.
        """

        pattern = r'("relation_type"\s*:\s*)([A-Z_]+)(\s*[\n,])'
        return re.sub(pattern, r'\1"\2"\3', raw)

    # -------------------------------------------------------------------------
    # Schema simplification
    # -------------------------------------------------------------------------

    def _simplify_schema(self, schema: dict) -> dict:
        """
        Simplify a Pydantic JSON schema for Ollama.

        Transformations:
        - Remove $defs and resolve $ref
        - Flatten nested references
        - Keep only: type, properties, items, required, description, title
        """
        if not isinstance(schema, dict):
            return schema

        defs = schema.get("$defs", {})

        def resolve_ref(obj: Any, defs: dict) -> Any:
            """Recursively resolve $ref entries."""
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]
                    if ref_path.startswith("#/$defs/"):
                        def_name = ref_path.split("/")[-1]
                        if def_name in defs:
                            resolved = defs[def_name].copy()
                            return resolve_ref(resolved, defs)
                    # Unknown ref -> keep as-is
                    return obj

                # Recurse on keys/values, skipping $defs
                return {k: resolve_ref(v, defs) for k, v in obj.items() if k != "$defs"}

            if isinstance(obj, list):
                return [resolve_ref(item, defs) for item in obj]

            return obj

        simplified = resolve_ref(schema, defs)

        # Keep only essential keys at the top level
        if isinstance(simplified, dict):
            essential_keys = {
                "type",
                "properties",
                "items",
                "required",
                "description",
                "title",
            }
            simplified = {k: v for k, v in simplified.items() if k in essential_keys}

            # If "required" is missing, consider all properties required.
            if "properties" in simplified and "required" not in simplified:
                simplified["required"] = list(simplified["properties"].keys())

        return simplified

    # -------------------------------------------------------------------------
    # Robust JSON extraction
    # -------------------------------------------------------------------------

    def _extract_json_from_response(self, text: str) -> dict:
        """
        Extract JSON from an Ollama response which may contain markdown.

        Handles:
        - ```json { ... } ```
        - ``` { ... } ```
        - Text with JSON inside
        - Plain JSON text
        """
        # Case 1: ```json ... ```
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                json_str = text[start:end].strip()
                return json.loads(json_str)

        # Case 2: ``` ... ```
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                json_str = text[start:end].strip()
                return json.loads(json_str)

        # Case 3: first '{' ... last '}'
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            json_str = text[first_brace : last_brace + 1]
            return json.loads(json_str)

        # Case 4: assume whole text is JSON
        return json.loads(text)

    # -------------------------------------------------------------------------
    # Deterministic canonicalization helper
    # -------------------------------------------------------------------------

    def _canonicalize_for_determinism(self, obj: Any) -> Any:
        """
        Return a version of `obj` with:
        - all dict keys sorted
        - recursively applied to nested dicts/lists

        We deliberately DO NOT sort lists generically, because list order
        often encodes semantics (e.g., a chain of causal edges).
        """
        if isinstance(obj, dict):
            return {
                k: self._canonicalize_for_determinism(obj[k])
                for k in sorted(obj.keys())
            }
        elif isinstance(obj, list):
            return [self._canonicalize_for_determinism(v) for v in obj]
        else:
            return obj

    # -------------------------------------------------------------------------
    # Main method: override generate_response
    # -------------------------------------------------------------------------

    async def generate_response(
        self,
        messages: list[Message],
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> dict | str:
        """
        Main entry point used by Graphiti.

        - If response_model is provided:
            * build a simplified schema from the Pydantic model
            * inject schema + EXAMPLE into the last message
            * call Ollama WITHOUT response_model (we control the call)
            * parse JSON, validate with Pydantic
            * if validation fails, return an "empty but valid" structure

        - If no response_model:
            * still call the model with deterministic sampling
            * return plain text
        """

        simplified_schema_for_fallback: dict[str, Any] | None = None

        # Optional: multilingual extraction instructions like base LLMClient
        group_id = kwargs.get("group_id")
        if messages:
            try:
                messages[0].content += get_extraction_language_instruction(group_id)
            except Exception:
                # If anything weird happens, don't break the call just for this
                pass

        # If Graphiti requested structured output, prepare the custom prompt
        if response_model is not None:
            try:
                original_schema = response_model.model_json_schema()
                simplified_schema = self._simplify_schema(original_schema)
                simplified_schema_for_fallback = simplified_schema

                schema_str = json.dumps(simplified_schema, indent=2)

                # Default example from schema
                example = self._create_example_from_schema(simplified_schema)
                example_str = json.dumps(example, indent=2, ensure_ascii=False)

                # Enhance the last user message
                if messages:
                    last_message = messages[-1]
                    enhanced_content = (
                        f"{last_message.content}\n\n"
                        f"CRITICAL: You MUST respond with ACTUAL DATA in JSON format, NOT the schema.\n\n"
                        f"Expected JSON structure:\n"
                        f"```json\n{schema_str}\n```\n\n"
                        f"EXAMPLE of a valid response (replace with real extracted data):\n"
                        f"```json\n{example_str}\n```\n\n"
                        f"STRICT REQUIREMENTS:\n"
                        f"1. Extract actual data from the text above\n"
                        f"2. Return ONLY the JSON data, NOT the schema definition\n"
                        f"3. Do NOT include $defs, $ref, properties, or other schema keywords\n"
                        f"4. Include all required fields with real values\n"
                        f"5. If no data found, use empty arrays [] where appropriate"
                    )
                    messages[-1] = Message(
                        role=last_message.role,
                        content=enhanced_content,
                    )

                logger.debug(f"📋 Simplified schema sent to model:\n{schema_str}")
                logger.debug(f"📋 Example sent to model:\n{example_str}")

            except Exception as e:
                logger.warning(
                    f"⚠️ Error while simplifying schema: {e}, "
                    f"falling back to standard behavior."
                )
                simplified_schema_for_fallback = None

        # Clean messages (same as base LLMClient would do)
        for m in messages:
            m.content = self._clean_input(m.content)

        # Deterministic-ish call to the OpenAI-compatible client
        try:
            # Build OpenAI-style messages
            openai_messages = []
            for m in messages:
                if m.role == "user":
                    openai_messages.append({"role": "user", "content": m.content})
                elif m.role == "system":
                    openai_messages.append({"role": "system", "content": m.content})

            # Deterministic sampling settings
            temperature = self.temperature if self.temperature is not None else 0.0

            response = await self.client.chat.completions.create(
                model=self.model or DEFAULT_MODEL,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                seed=0,
                # Vendor-specific knobs for Ollama / OpenAI shim
                extra_body={
                    "top_k": 0,            # neutralize top-k sampling
                    "repeat_penalty": 1.0  # no repetition penalty
                },
            )

            raw_response = response.choices[0].message.content or ""

            # If Graphiti didn't ask for structured output, just return raw text
            if response_model is None:
                return raw_response

            # From here on we expect JSON-ish text

            # If we get a string, we must parse JSON from it
            if isinstance(raw_response, str):
                parsed = None
                first_error: Exception | None = None
                try:
                    parsed = self._extract_json_from_response(raw_response)
                except Exception as e:
                    first_error = e
                    # Try to repair unquoted relation_type values and retry once
                    repaired = self._quote_relation_types(raw_response)
                    try:
                        parsed = self._extract_json_from_response(repaired)
                        logger.warning(
                            "⚠️ JSON parse recovered after quoting relation_type (was: %s)",
                            first_error,
                        )
                    except Exception:
                        logger.error(f"❌ JSON parsing error from Ollama: {e}")
                        logger.error(f"Raw text:\n{raw_response}")
                        # Fallback to empty structure if possible
                        if simplified_schema_for_fallback is not None:
                            empty = self._create_empty_from_schema(
                                simplified_schema_for_fallback
                            )
                            logger.warning(
                                f"⚠️ Using empty fallback structure instead: {empty}"
                            )
                            return empty
                        raise

                # Try to validate with Pydantic *inside the client* first
                try:
                    validated = response_model(**parsed)
                    logger.debug("✅ Ollama response validated successfully")
                    out = validated.model_dump()
                    out = self._canonicalize_for_determinism(out)
                    return out
                except Exception as e:
                    logger.error(
                        f"❌ Pydantic validation failed inside client: {e}"
                    )
                    logger.error(
                        f"Parsed response:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}"
                    )

                    # Fallback: return an empty but valid structure
                    if simplified_schema_for_fallback is not None:
                        empty = self._create_empty_from_schema(
                            simplified_schema_for_fallback
                        )
                        logger.warning(
                            f"⚠️ Using empty fallback structure instead: {empty}"
                        )
                        return empty

                    # Last resort: return parsed as-is
                    return parsed

            # If for some reason we got a dict already
            if isinstance(raw_response, dict):
                if response_model is not None:
                    try:
                        validated = response_model(**raw_response)
                        logger.debug(
                            "✅ Ollama dict response validated successfully"
                        )
                        out = validated.model_dump()
                        out = self._canonicalize_for_determinism(out)
                        return out
                    except Exception as e:
                        logger.error(
                            f"❌ Pydantic validation (dict) failed inside client: {e}"
                        )
                        logger.error(
                            f"Raw dict response:\n{json.dumps(raw_response, indent=2, ensure_ascii=False)}"
                        )
                        if simplified_schema_for_fallback is not None:
                            empty = self._create_empty_from_schema(
                                simplified_schema_for_fallback
                            )
                            logger.warning(
                                f"⚠️ Using empty fallback structure instead: {empty}"
                            )
                            return empty
                return raw_response

            # Fallback: unknown type, just return what we got
            logger.warning(
                f"⚠️ Unexpected response type from Ollama: {type(raw_response)}"
            )
            return raw_response

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSONDecodeError from Ollama: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error during Ollama generate_response: {e}")
            raise
