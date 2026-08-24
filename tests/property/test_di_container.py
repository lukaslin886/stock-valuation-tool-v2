"""DI Container 生命週期正確性屬性測試。

Feature: stock-valuation-optimization, Property 14: DI Container lifecycle correctness

使用 Hypothesis 驗證 DI Container 的生命週期不變式：
- 註冊為 SINGLETON 的服務，多次 resolve() 回傳相同物件（is identity）
- 註冊為 TRANSIENT 的服務，連續 resolve() 回傳不同物件（is not）

Strategy: 產生隨機的 resolve 呼叫次數（2-10），驗證兩種生命週期的不變式。

**Validates: Requirements 1.1, 1.4**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.container import Container, Lifetime


class TestDIContainerLifecycleProperty:
    """Property 14: DI Container 生命週期正確性。

    驗證 singleton 多次 resolve 回傳相同物件、transient 回傳不同物件。
    """

    @given(n_resolves=st.integers(min_value=2, max_value=10))
    @settings(max_examples=200, deadline=30000)
    def test_singleton_identity(self, n_resolves: int) -> None:
        """Singleton 生命週期：多次 resolve 回傳相同物件實體。

        For any service registered as SINGLETON, multiple resolve() calls
        SHALL return the same object (is identity).

        **Validates: Requirements 1.1**
        """
        container = Container()

        class ServiceA:
            pass

        container.register(ServiceA, lambda: ServiceA(), Lifetime.SINGLETON)
        instances = [container.resolve(ServiceA) for _ in range(n_resolves)]

        # All instances should be the same object
        for inst in instances[1:]:
            assert inst is instances[0]

    @given(n_resolves=st.integers(min_value=2, max_value=10))
    @settings(max_examples=200, deadline=30000)
    def test_transient_different_instances(self, n_resolves: int) -> None:
        """Transient 生命週期：連續 resolve 回傳不同物件實體。

        For any service registered as TRANSIENT, consecutive resolve() calls
        SHALL return different objects (is not).

        **Validates: Requirements 1.4**
        """
        container = Container()

        class ServiceB:
            pass

        container.register(ServiceB, lambda: ServiceB(), Lifetime.TRANSIENT)
        instances = [container.resolve(ServiceB) for _ in range(n_resolves)]

        # All instances should be different objects
        for i in range(len(instances)):
            for j in range(i + 1, len(instances)):
                assert instances[i] is not instances[j]
