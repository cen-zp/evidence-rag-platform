from app.schemas.chat import ChatUsage
from app.services.model_usage import _calculate_estimated_cost


def test_estimated_cost_uses_the_recorded_price_snapshot() -> None:
    cost = _calculate_estimated_cost(
        ChatUsage(prompt_tokens=1_500_000, completion_tokens=500_000, total_tokens=2_000_000),
        input_cost_per_million_tokens=2.0,
        output_cost_per_million_tokens=4.0,
    )

    assert cost == 5.0


def test_estimated_cost_is_unavailable_without_usage_or_both_prices() -> None:
    usage = ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    assert _calculate_estimated_cost(None, 2.0, 4.0) is None
    assert _calculate_estimated_cost(usage, None, 4.0) is None
    assert _calculate_estimated_cost(usage, 2.0, None) is None
