from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas.strategies import StrategyParameterMetadata


def build_strategy_parameters(params_model: type[BaseModel]) -> dict[str, StrategyParameterMetadata]:
    schema = params_model.model_json_schema()
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    parameters: dict[str, StrategyParameterMetadata] = {}

    for name, property_schema in properties.items():
        parameters[name] = StrategyParameterMetadata(
            type=property_schema["type"],
            default=property_schema.get("default"),
            required=name in required_fields,
            minimum=property_schema.get("minimum"),
            maximum=property_schema.get("maximum"),
            exclusiveMinimum=property_schema.get("exclusiveMinimum"),
            exclusiveMaximum=property_schema.get("exclusiveMaximum"),
            minLength=property_schema.get("minLength"),
            maxLength=property_schema.get("maxLength"),
            pattern=property_schema.get("pattern"),
        )

    return parameters
