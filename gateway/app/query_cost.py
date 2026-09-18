from __future__ import annotations

from typing import Optional

from graphql import GraphQLError
from graphql.language import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionSetNode,
)
from graphql.validation import ValidationContext, ValidationRule
from strawberry.extensions import AddValidationRules
from strawberry.extensions.utils import is_introspection_key


class QueryCostLimiter(AddValidationRules):
    """Bloqueia consultas cujo custo total (soma de pesos por campo) excede um limite.

    Complementa o QueryDepthLimiter: profundidade não pega ataques por largura
    (ex.: muitos campos irmãos ou aliases repetidos no mesmo nível), que a soma
    de pesos por campo captura.

    Example:
    ```python
    schema = strawberry.Schema(
        Query,
        extensions=[QueryCostLimiter(max_cost=50, field_costs={"pedidos": 5, "produtos": 5})],
    )
    ```
    """

    def __init__(
        self,
        max_cost: int,
        field_costs: Optional[dict[str, int]] = None,
        default_cost: int = 1,
    ) -> None:
        validator = _create_cost_validator(max_cost, field_costs or {}, default_cost)
        super().__init__([validator])


def _create_cost_validator(
    max_cost: int,
    field_costs: dict[str, int],
    default_cost: int,
) -> type[ValidationRule]:
    class QueryCostValidator(ValidationRule):
        def __init__(self, validation_context: ValidationContext) -> None:
            document = validation_context.document
            fragments = {
                definition.name.value: definition
                for definition in document.definitions
                if isinstance(definition, FragmentDefinitionNode)
            }

            for definition in document.definitions:
                if isinstance(definition, OperationDefinitionNode):
                    cost = _selection_set_cost(
                        definition.selection_set, fragments, field_costs, default_cost
                    )
                    if cost > max_cost:
                        validation_context.report_error(
                            GraphQLError(
                                f"Custo da consulta ({cost}) excede o limite "
                                f"máximo permitido ({max_cost}).",
                                [definition],
                            )
                        )
            super().__init__(validation_context)

    return QueryCostValidator


def _selection_set_cost(
    selection_set: Optional[SelectionSetNode],
    fragments: dict[str, FragmentDefinitionNode],
    field_costs: dict[str, int],
    default_cost: int,
) -> int:
    if selection_set is None:
        return 0

    total = 0
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            if is_introspection_key(selection.name.value):
                continue
            weight = field_costs.get(selection.name.value, default_cost)
            total += weight + _selection_set_cost(
                selection.selection_set, fragments, field_costs, default_cost
            )
        elif isinstance(selection, FragmentSpreadNode):
            fragment = fragments.get(selection.name.value)
            if fragment is not None:
                total += _selection_set_cost(
                    fragment.selection_set, fragments, field_costs, default_cost
                )
        elif isinstance(selection, InlineFragmentNode):
            total += _selection_set_cost(
                selection.selection_set, fragments, field_costs, default_cost
            )
    return total


__all__ = ["QueryCostLimiter"]
