import numpy as np


class ScenarioGenerator:
    functions = {
        "normal": np.random.normal,
        "binomial": np.random.binomial,
        "poisson": np.random.poisson,
        "uniform": np.random.uniform,
        "exponential": np.random.exponential,
        "gamma": np.random.gamma,
        "beta": np.random.beta,
        "geometric": np.random.geometric,
        "lognormal": np.random.lognormal,
    }

    defaults = {
        "normal": {"loc": 0, "scale": 1},
        "binomial": {"n": 10, "p": 0.5},
        "poisson": {"lam": 5},
        "uniform": {"low": 0.0, "high": 1.0},
        "exponential": {"scale": 1.0},
        "gamma": {"shape": 2.0, "scale": 2.0},
        "beta": {"a": 2.0, "b": 5.0},
        "geometric": {"p": 0.5},
        "lognormal": {"mean": 0.0, "sigma": 1.0},
    }

    def __init__(self, fns: list[str]):
        self.funcs = {fn: self.functions[fn] for fn in fns if fn in self.functions}

    def get_scenario(self, amount: int, fn: str) -> list[float] | None:
        if fn not in self.funcs or amount == 0:
            return None
        return self.funcs[fn](size=amount, **self.defaults[fn]).tolist()
