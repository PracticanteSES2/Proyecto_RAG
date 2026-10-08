from src.semantic.filter_resolver import (
    FilterResolver,
)
from src.semantic.business_filter_resolver import (
    BusinessFilterResolver,
)
from src.dax.dax_validator import (
    DAXValidator,
)


class _ResolverCache:

    def __init__(
        self,
        source_router,
        default_semantic_model=None,
    ):
        self.source_router = (
            source_router
        )
        self.default_semantic_model = (
            default_semantic_model
        )
        self._cache = {}

    def _resolve_model(
        self,
        semantic_model=None,
        question=None,
        dashboard=None,
    ):
        if semantic_model:
            return semantic_model

        context = (
            self.source_router
            .resolve(
                question=
                    question,
                dashboard=
                    dashboard,
            )
        )

        if (
            context.get(
                "status"
            )
            == "resolved"
            and context.get(
                "semantic_model"
            )
        ):
            return context[
                "semantic_model"
            ]

        return (
            self.default_semantic_model
        )

    def _catalog_path(
        self,
        semantic_model,
    ):
        return (
            self.source_router
            .catalog_path_for_model(
                semantic_model,
                required=True,
            )
        )


class MultiModelFilterResolver(
    _ResolverCache
):

    def __init__(
        self,
        source_router,
        default_semantic_model=None,
    ):
        super().__init__(
            source_router=
                source_router,
            default_semantic_model=
                default_semantic_model,
        )

    def _resolver(
        self,
        semantic_model,
    ):
        if semantic_model not in self._cache:
            self._cache[
                semantic_model
            ] = FilterResolver(
                self._catalog_path(
                    semantic_model
                )
            )

        return self._cache[
            semantic_model
        ]

    def resolve(
        self,
        intent_result,
        semantic_model=None,
        dashboard=None,
    ):
        question = (
            intent_result.get(
                "original_question"
            )
            or ""
        )

        dashboard = (
            dashboard
            or intent_result.get(
                "dashboard"
            )
        )

        model = self._resolve_model(
            semantic_model=
                semantic_model,
            question=
                question,
            dashboard=
                dashboard,
        )

        if not model:
            return {
                "status":
                    "error",
                "reason":
                    "semantic_model_not_resolved",
                "filters":
                    [],
            }

        result = (
            self._resolver(
                model
            )
            .resolve(
                intent_result
            )
        )

        if isinstance(
            result,
            dict,
        ):
            result.setdefault(
                "semantic_model",
                model,
            )

        return result


class MultiModelBusinessFilterResolver(
    _ResolverCache
):
    # Mantener compatibilidad con QuerySemanticPlanner.
    CONCEPTS = (
        BusinessFilterResolver
        .CONCEPTS
    )

    def __init__(
        self,
        source_router,
        powerbi_provider,
        default_semantic_model=None,
    ):
        super().__init__(
            source_router=
                source_router,
            default_semantic_model=
                default_semantic_model,
        )

        self.powerbi_provider = (
            powerbi_provider
        )

    def _resolver(
        self,
        semantic_model,
    ):
        if semantic_model not in self._cache:
            self._cache[
                semantic_model
            ] = (
                BusinessFilterResolver(
                    self._catalog_path(
                        semantic_model
                    ),
                    self.powerbi_provider,
                )
            )

        return self._cache[
            semantic_model
        ]

    def preload_domains(
        self,
        semantic_model,
        dashboard,
    ):
        return (
            self._resolver(
                semantic_model
            )
            .preload_domains(
                semantic_model,
                dashboard,
            )
        )

    def _find_column(
        self,
        concept,
        dashboard,
        semantic_model=None,
    ):
        model = self._resolve_model(
            semantic_model=
                semantic_model,
            dashboard=
                dashboard,
        )

        if not model:
            return None

        return (
            self._resolver(
                model
            )
            ._find_column(
                concept,
                dashboard,
            )
        )

    def _get_values(
        self,
        semantic_model,
        table,
        column,
    ):
        return (
            self._resolver(
                semantic_model
            )
            ._get_values(
                semantic_model,
                table,
                column,
            )
        )

    def resolve(
        self,
        question,
        dashboard,
        semantic_model=None,
    ):
        model = self._resolve_model(
            semantic_model=
                semantic_model,
            question=
                question,
            dashboard=
                dashboard,
        )

        if not model:
            return {
                "status":
                    "error",
                "reason":
                    "semantic_model_not_resolved",
                "filters":
                    [],
            }

        result = (
            self._resolver(
                model
            )
            .resolve(
                question=
                    question,
                dashboard=
                    dashboard,
                semantic_model=
                    model,
            )
        )

        if isinstance(
            result,
            dict,
        ):
            result.setdefault(
                "semantic_model",
                model,
            )

        return result


class MultiModelDAXValidator(
    _ResolverCache
):

    def __init__(
        self,
        source_router,
        default_semantic_model=None,
    ):
        super().__init__(
            source_router=
                source_router,
            default_semantic_model=
                default_semantic_model,
        )

    def _validator(
        self,
        semantic_model,
    ):
        if semantic_model not in self._cache:
            self._cache[
                semantic_model
            ] = DAXValidator(
                self._catalog_path(
                    semantic_model
                )
            )

        return self._cache[
            semantic_model
        ]

    def validate(
        self,
        dax_result,
        metric_result,
        filter_result,
        semantic_model=None,
    ):
        model = (
            semantic_model
            or metric_result.get(
                "semantic_model"
            )
            or self.default_semantic_model
        )

        if not model:
            return {
                "valid":
                    False,
                "errors": [
                    (
                        "No se pudo determinar "
                        "el modelo semántico."
                    )
                ],
            }

        result = (
            self._validator(
                model
            )
            .validate(
                dax_result,
                metric_result,
                filter_result,
            )
        )

        if isinstance(
            result,
            dict,
        ):
            result.setdefault(
                "semantic_model",
                model,
            )

        return result
