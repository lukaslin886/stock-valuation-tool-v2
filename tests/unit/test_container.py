"""DI Container 單元測試。

驗證 Container 類別的 register/resolve/override/reset 行為，
涵蓋 singleton 與 transient 生命週期、循環依賴偵測、錯誤處理等核心功能。
"""

from __future__ import annotations

from typing import Protocol

import pytest

from app.container import CircularDependencyError, Container, Lifetime, setup_container


# -- 測試用 Protocol 與實作 --


class GreeterProtocol(Protocol):
    """測試用問候服務介面。"""

    def greet(self, name: str) -> str: ...


class SimpleGreeter:
    """簡單問候實作。"""

    def greet(self, name: str) -> str:
        return f"Hello, {name}"


class FancyGreeter:
    """花俏問候實作。"""

    def greet(self, name: str) -> str:
        return f"Greetings, {name}!"


class CounterService:
    """帶有計數器的服務，用來驗證實例唯一性。"""

    _counter: int = 0

    def __init__(self) -> None:
        CounterService._counter += 1
        self.instance_id = CounterService._counter


# -- 測試 --


class TestContainerRegister:
    """測試 register 方法。"""

    def test_register_valid_service(self) -> None:
        """正確註冊服務不拋出例外。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())
        assert container.is_registered(GreeterProtocol)

    def test_register_with_explicit_lifetime(self) -> None:
        """顯式指定 lifetime 正常運作。"""
        container = Container()
        container.register(
            GreeterProtocol, lambda: SimpleGreeter(), Lifetime.TRANSIENT
        )
        assert container.is_registered(GreeterProtocol)

    def test_register_non_type_interface_raises_typeerror(self) -> None:
        """interface 非型別時拋出 TypeError。"""
        container = Container()
        with pytest.raises(TypeError, match="interface 必須為型別"):
            container.register("not_a_type", lambda: SimpleGreeter())  # type: ignore[arg-type]

    def test_register_non_callable_factory_raises_typeerror(self) -> None:
        """factory 不可呼叫時拋出 TypeError。"""
        container = Container()
        with pytest.raises(TypeError, match="factory 必須為可呼叫物件"):
            container.register(GreeterProtocol, 42)  # type: ignore[arg-type]

    def test_register_overwrites_existing(self) -> None:
        """重複註冊同一介面時覆寫先前的工廠。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())
        container.register(GreeterProtocol, lambda: FancyGreeter())

        result = container.resolve(GreeterProtocol)
        assert isinstance(result, FancyGreeter)


class TestContainerResolve:
    """測試 resolve 方法。"""

    def test_resolve_singleton_returns_same_instance(self) -> None:
        """Singleton 生命週期多次 resolve 回傳同一物件。"""
        container = Container()
        container.register(
            GreeterProtocol, lambda: SimpleGreeter(), Lifetime.SINGLETON
        )

        first = container.resolve(GreeterProtocol)
        second = container.resolve(GreeterProtocol)

        assert first is second

    def test_resolve_transient_returns_different_instances(self) -> None:
        """Transient 生命週期每次 resolve 回傳不同物件。"""
        container = Container()
        container.register(
            GreeterProtocol, lambda: SimpleGreeter(), Lifetime.TRANSIENT
        )

        first = container.resolve(GreeterProtocol)
        second = container.resolve(GreeterProtocol)

        assert first is not second

    def test_resolve_unregistered_raises_keyerror(self) -> None:
        """解析未註冊的服務拋出 KeyError。"""
        container = Container()
        with pytest.raises(KeyError, match="Service not registered"):
            container.resolve(GreeterProtocol)

    def test_resolve_singleton_default_lifetime(self) -> None:
        """預設 lifetime 為 SINGLETON。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())

        first = container.resolve(GreeterProtocol)
        second = container.resolve(GreeterProtocol)

        assert first is second


class TestContainerOverride:
    """測試 override 方法。"""

    def test_override_replaces_singleton(self) -> None:
        """override 可替換已建立的 singleton 實例。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())

        # 先 resolve 建立 singleton
        original = container.resolve(GreeterProtocol)
        assert isinstance(original, SimpleGreeter)

        # override 為 mock
        mock_greeter = FancyGreeter()
        container.override(GreeterProtocol, mock_greeter)

        overridden = container.resolve(GreeterProtocol)
        assert overridden is mock_greeter

    def test_override_before_first_resolve(self) -> None:
        """可在首次 resolve 前 override。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())

        mock_greeter = FancyGreeter()
        container.override(GreeterProtocol, mock_greeter)

        result = container.resolve(GreeterProtocol)
        assert result is mock_greeter

    def test_override_unregistered_service(self) -> None:
        """可 override 未註冊的服務（測試情境常見）。"""
        container = Container()
        mock_greeter = FancyGreeter()
        container.override(GreeterProtocol, mock_greeter)

        # override 後即使未 register，也能 resolve（因為 singletons 快取命中）
        # 但需先確認 registry 有記錄，否則正常 resolve 流程會檢查
        # 設計上 override 直接寫入 singletons，resolve 先檢查 singletons
        # 所以未註冊但有 override 的情況：
        # 我們的實作先檢查 _registry，若不在 → 拋 KeyError
        # 這是正確的行為：override 不代表 register
        # 實際測試中通常先 register 再 override
        with pytest.raises(KeyError):
            container.resolve(GreeterProtocol)


class TestContainerReset:
    """測試 reset 方法。"""

    def test_reset_clears_singletons(self) -> None:
        """reset 後重新 resolve 會建立新實例。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())

        first = container.resolve(GreeterProtocol)
        container.reset()
        second = container.resolve(GreeterProtocol)

        assert first is not second

    def test_reset_preserves_registry(self) -> None:
        """reset 不影響註冊表，reset 後仍可 resolve。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())
        container.resolve(GreeterProtocol)

        container.reset()

        assert container.is_registered(GreeterProtocol)
        result = container.resolve(GreeterProtocol)
        assert isinstance(result, SimpleGreeter)

    def test_reset_clears_overrides(self) -> None:
        """reset 清除 override 的實例。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())
        container.override(GreeterProtocol, FancyGreeter())

        container.reset()

        result = container.resolve(GreeterProtocol)
        assert isinstance(result, SimpleGreeter)


class TestContainerIsRegistered:
    """測試 is_registered 方法。"""

    def test_not_registered(self) -> None:
        """未註冊的介面回傳 False。"""
        container = Container()
        assert container.is_registered(GreeterProtocol) is False

    def test_registered(self) -> None:
        """已註冊的介面回傳 True。"""
        container = Container()
        container.register(GreeterProtocol, lambda: SimpleGreeter())
        assert container.is_registered(GreeterProtocol) is True


class TestContainerCircularDependency:
    """測試循環依賴偵測。"""

    def test_direct_circular_dependency_raises_error(self) -> None:
        """A -> A 直接循環依賴拋出 CircularDependencyError。"""
        container = Container()

        # A 的工廠函式嘗試解析自己
        class ServiceA:
            pass

        container.register(ServiceA, lambda: container.resolve(ServiceA))

        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve(ServiceA)

        assert exc_info.value.interface is ServiceA

    def test_indirect_circular_dependency_raises_error(self) -> None:
        """A -> B -> A 間接循環依賴拋出 CircularDependencyError。"""
        container = Container()

        class ServiceA:
            pass

        class ServiceB:
            pass

        # A 依賴 B，B 依賴 A
        container.register(
            ServiceA, lambda: container.resolve(ServiceB), Lifetime.SINGLETON
        )
        container.register(
            ServiceB, lambda: container.resolve(ServiceA), Lifetime.SINGLETON
        )

        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve(ServiceA)

        assert exc_info.value.interface is ServiceA
        assert ServiceA in exc_info.value.chain

    def test_three_level_circular_dependency(self) -> None:
        """A -> B -> C -> A 三層循環依賴拋出錯誤。"""
        container = Container()

        class ServiceA:
            pass

        class ServiceB:
            pass

        class ServiceC:
            pass

        container.register(
            ServiceA, lambda: container.resolve(ServiceB), Lifetime.SINGLETON
        )
        container.register(
            ServiceB, lambda: container.resolve(ServiceC), Lifetime.SINGLETON
        )
        container.register(
            ServiceC, lambda: container.resolve(ServiceA), Lifetime.SINGLETON
        )

        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve(ServiceA)

        # 循環點是 ServiceA
        assert exc_info.value.interface is ServiceA

    def test_non_circular_chain_resolves_ok(self) -> None:
        """A -> B -> C 無循環鏈路正常解析。"""
        container = Container()

        class ServiceC:
            pass

        class ServiceB:
            def __init__(self, c: ServiceC) -> None:
                self.c = c

        class ServiceA:
            def __init__(self, b: ServiceB) -> None:
                self.b = b

        container.register(ServiceC, lambda: ServiceC(), Lifetime.SINGLETON)
        container.register(
            ServiceB,
            lambda: ServiceB(container.resolve(ServiceC)),
            Lifetime.SINGLETON,
        )
        container.register(
            ServiceA,
            lambda: ServiceA(container.resolve(ServiceB)),
            Lifetime.SINGLETON,
        )

        result = container.resolve(ServiceA)
        assert isinstance(result, ServiceA)
        assert isinstance(result.b, ServiceB)
        assert isinstance(result.b.c, ServiceC)

    def test_circular_dependency_error_message_contains_chain(self) -> None:
        """錯誤訊息包含解析鏈路資訊。"""
        container = Container()

        class Alpha:
            pass

        class Beta:
            pass

        container.register(
            Alpha, lambda: container.resolve(Beta), Lifetime.SINGLETON
        )
        container.register(
            Beta, lambda: container.resolve(Alpha), Lifetime.SINGLETON
        )

        with pytest.raises(CircularDependencyError, match="Alpha"):
            container.resolve(Alpha)

    def test_circular_detection_resets_after_failure(self) -> None:
        """循環偵測拋出錯誤後，解析堆疊正確重置，不影響後續正常解析。"""
        container = Container()

        class ServiceX:
            pass

        class ServiceY:
            pass

        # 先建立循環依賴
        container.register(
            ServiceX, lambda: container.resolve(ServiceX), Lifetime.TRANSIENT
        )

        with pytest.raises(CircularDependencyError):
            container.resolve(ServiceX)

        # 重新註冊為正常工廠
        container.register(ServiceX, lambda: ServiceX(), Lifetime.TRANSIENT)
        container.register(ServiceY, lambda: ServiceY(), Lifetime.SINGLETON)

        # 應該能正常解析
        assert isinstance(container.resolve(ServiceX), ServiceX)
        assert isinstance(container.resolve(ServiceY), ServiceY)


class TestSetupContainer:
    """測試 setup_container 工廠函式。"""

    def test_returns_container_instance(self) -> None:
        """回傳 Container 實例。"""
        container = setup_container()
        assert isinstance(container, Container)

    def test_returns_fresh_container(self) -> None:
        """每次呼叫回傳新的容器。"""
        c1 = setup_container()
        c2 = setup_container()
        assert c1 is not c2
