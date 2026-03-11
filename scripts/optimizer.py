"""
遗传算法参数寻优器

用户说 "帮我找到最优参数"，Agent 用这个模块自动搜索最优参数组合。

流程：
  1. 定义参数空间（如 fast_period: 5-30, stop_loss_pct: 1%-10%）
  2. 初始化随机种群
  3. 每代：评估适应度（跑回测取夏普比率）→ 选择 → 交叉 → 变异
  4. 输出最优参数 + 对应回测结果

示例:
    space = ParameterSpace()
    space.add_int("fast_period", 5, 30)
    space.add_int("slow_period", 20, 100)
    space.add_float("stop_loss_pct", 0.01, 0.10)

    optimizer = GeneticOptimizer(space, fitness_fn=my_backtest_fn)
    result = optimizer.run()
    print(result.best_params)    # {"fast_period": 12, "slow_period": 45, ...}
    print(result.best_fitness)   # 2.35 (Sharpe ratio)
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger


# ═══════════════════════════════════════════
#  参数空间定义
# ═══════════════════════════════════════════

@dataclass
class ParamDef:
    """单个参数的定义"""
    name: str
    param_type: str       # "int" / "float" / "choice"
    low: float = 0
    high: float = 1
    choices: list = field(default_factory=list)

    def random_value(self):
        if self.param_type == "int":
            return random.randint(int(self.low), int(self.high))
        elif self.param_type == "float":
            return round(random.uniform(self.low, self.high), 6)
        elif self.param_type == "choice":
            return random.choice(self.choices)

    def mutate(self, value, strength: float = 0.2):
        if self.param_type == "int":
            range_size = max(1, int((self.high - self.low) * strength))
            new_val = value + random.randint(-range_size, range_size)
            return max(int(self.low), min(int(self.high), int(new_val)))
        elif self.param_type == "float":
            range_size = (self.high - self.low) * strength
            new_val = value + random.uniform(-range_size, range_size)
            return round(max(self.low, min(self.high, new_val)), 6)
        elif self.param_type == "choice":
            return random.choice(self.choices)


class ParameterSpace:
    """
    定义策略的可调参数空间。

    示例:
        space = ParameterSpace()
        space.add_int("fast_period", 5, 30)
        space.add_int("slow_period", 20, 100)
        space.add_float("stop_loss_pct", 0.01, 0.10)
        space.add_float("take_profit_pct", 0.05, 0.30)
        space.add_int("leverage", 1, 10)
        space.add_choice("margin_mode", ["isolated", "cross"])
    """

    def __init__(self):
        self.params: list[ParamDef] = []

    def add_int(self, name: str, low: int, high: int):
        self.params.append(ParamDef(name, "int", low, high))
        return self

    def add_float(self, name: str, low: float, high: float):
        self.params.append(ParamDef(name, "float", low, high))
        return self

    def add_choice(self, name: str, choices: list):
        self.params.append(ParamDef(name, "choice", choices=choices))
        return self

    def random_individual(self) -> dict:
        return {p.name: p.random_value() for p in self.params}

    def param_names(self) -> list[str]:
        return [p.name for p in self.params]

    def get_param(self, name: str) -> Optional[ParamDef]:
        for p in self.params:
            if p.name == name:
                return p
        return None


# ═══════════════════════════════════════════
#  寻优结果
# ═══════════════════════════════════════════

@dataclass
class OptimizationResult:
    """寻优结果"""
    best_params: dict
    best_fitness: float
    generations_log: list[dict] = field(default_factory=list)
    all_evaluated: list[tuple[dict, float]] = field(default_factory=list)

    def top_n(self, n: int = 10) -> list[tuple[dict, float]]:
        """返回适应度最高的 N 组参数"""
        sorted_results = sorted(self.all_evaluated, key=lambda x: x[1], reverse=True)
        return sorted_results[:n]

    def summary(self) -> str:
        lines = [
            "═══ 遗传寻优结果 ═══",
            f"  最优适应度: {self.best_fitness:.4f}",
            f"  搜索代数: {len(self.generations_log)}",
            f"  总评估次数: {len(self.all_evaluated)}",
            "",
            "  最优参数:",
        ]
        for k, v in self.best_params.items():
            if isinstance(v, float):
                lines.append(f"    {k}: {v:.6f}")
            else:
                lines.append(f"    {k}: {v}")

        lines.append("")
        lines.append("  Top 5 参数组:")
        for i, (params, fitness) in enumerate(self.top_n(5), 1):
            params_str = ", ".join(
                f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                for k, v in params.items()
            )
            lines.append(f"    [{i}] fitness={fitness:.4f} | {params_str}")

        if self.generations_log:
            lines.append("")
            lines.append("  收敛历史:")
            step = max(1, len(self.generations_log) // 10)
            for i, gen in enumerate(self.generations_log):
                if i % step == 0 or i == len(self.generations_log) - 1:
                    lines.append(
                        f"    Gen {gen['generation']:3d}: best={gen['best_fitness']:.4f} "
                        f"avg={gen['avg_fitness']:.4f}")

        return "\n".join(lines)


# ═══════════════════════════════════════════
#  遗传算法核心
# ═══════════════════════════════════════════

class GeneticOptimizer:
    """
    遗传算法参数寻优器。

    fitness_fn 签名: (params: dict) -> float
      接收参数字典，返回适应度分数（越高越好）。
      通常 Agent 会在 fitness_fn 中构建策略 → 跑回测 → 返回夏普比率。

    示例:
        def fitness_fn(params):
            strategy = build_ma_cross_strategy(
                fast_period=params["fast_period"],
                slow_period=params["slow_period"],
                leverage=params["leverage"],
                stop_loss_pct=params["stop_loss_pct"],
            )
            # ... 跑回测 ...
            return metrics["sharpe_ratio"]

        optimizer = GeneticOptimizer(
            space=space,
            fitness_fn=fitness_fn,
            population_size=50,
            generations=30,
        )
        result = optimizer.run()
    """

    def __init__(
        self,
        space: ParameterSpace,
        fitness_fn: Callable[[dict], float],
        population_size: int = 50,
        generations: int = 30,
        elite_ratio: float = 0.1,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.15,
        mutation_strength: float = 0.2,
        early_stop_generations: int = 10,
        seed: Optional[int] = None,
    ):
        self.space = space
        self.fitness_fn = fitness_fn
        self.population_size = population_size
        self.generations = generations
        self.elite_ratio = elite_ratio
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.mutation_strength = mutation_strength
        self.early_stop_generations = early_stop_generations

        if seed is not None:
            random.seed(seed)

    def _init_population(self) -> list[dict]:
        return [self.space.random_individual() for _ in range(self.population_size)]

    def _evaluate(self, population: list[dict]) -> list[tuple[dict, float]]:
        results = []
        for individual in population:
            try:
                fitness = self.fitness_fn(individual)
                if fitness is None or not isinstance(fitness, (int, float)):
                    fitness = -999.0
            except Exception as e:
                logger.warning(f"评估失败: {individual} → {e}")
                fitness = -999.0
            results.append((copy.deepcopy(individual), float(fitness)))
        return results

    def _select_parents(self, evaluated: list[tuple[dict, float]]) -> list[dict]:
        """锦标赛选择"""
        parents = []
        tournament_size = min(3, len(evaluated))
        for _ in range(len(evaluated)):
            contestants = random.sample(evaluated, tournament_size)
            winner = max(contestants, key=lambda x: x[1])
            parents.append(copy.deepcopy(winner[0]))
        return parents

    def _crossover(self, parent_a: dict, parent_b: dict) -> tuple[dict, dict]:
        """均匀交叉"""
        child_a, child_b = copy.deepcopy(parent_a), copy.deepcopy(parent_b)
        for key in parent_a:
            if random.random() < 0.5:
                child_a[key], child_b[key] = child_b[key], child_a[key]
        return child_a, child_b

    def _mutate(self, individual: dict) -> dict:
        """变异"""
        mutated = copy.deepcopy(individual)
        for param_def in self.space.params:
            if random.random() < self.mutation_rate:
                mutated[param_def.name] = param_def.mutate(
                    mutated[param_def.name], self.mutation_strength)
        return mutated

    def run(self) -> OptimizationResult:
        """执行遗传寻优，返回结果。"""
        logger.info(f"开始遗传寻优: {self.population_size}个体 × {self.generations}代")
        logger.info(f"参数空间: {[p.name for p in self.space.params]}")

        population = self._init_population()
        all_evaluated: list[tuple[dict, float]] = []
        generations_log: list[dict] = []
        best_fitness = -float("inf")
        best_params = {}
        no_improve_count = 0

        for gen in range(self.generations):
            evaluated = self._evaluate(population)
            all_evaluated.extend(evaluated)

            fitnesses = [f for _, f in evaluated]
            gen_best_idx = max(range(len(fitnesses)), key=lambda i: fitnesses[i])
            gen_best_fitness = fitnesses[gen_best_idx]
            gen_best_params = evaluated[gen_best_idx][0]
            gen_avg_fitness = sum(fitnesses) / len(fitnesses)

            generations_log.append({
                "generation": gen,
                "best_fitness": gen_best_fitness,
                "avg_fitness": gen_avg_fitness,
                "best_params": copy.deepcopy(gen_best_params),
            })

            if gen_best_fitness > best_fitness:
                best_fitness = gen_best_fitness
                best_params = copy.deepcopy(gen_best_params)
                no_improve_count = 0
                logger.info(f"Gen {gen:3d} | best={best_fitness:.4f} avg={gen_avg_fitness:.4f} ★ 新最优")
            else:
                no_improve_count += 1
                if gen % 5 == 0:
                    logger.info(f"Gen {gen:3d} | best={gen_best_fitness:.4f} avg={gen_avg_fitness:.4f}")

            if no_improve_count >= self.early_stop_generations:
                logger.info(f"连续 {self.early_stop_generations} 代无提升，提前终止")
                break

            evaluated.sort(key=lambda x: x[1], reverse=True)
            elite_count = max(1, int(self.population_size * self.elite_ratio))
            new_population = [copy.deepcopy(e[0]) for e in evaluated[:elite_count]]

            parents = self._select_parents(evaluated)

            while len(new_population) < self.population_size:
                p1, p2 = random.sample(parents, 2)
                if random.random() < self.crossover_rate:
                    c1, c2 = self._crossover(p1, p2)
                else:
                    c1, c2 = copy.deepcopy(p1), copy.deepcopy(p2)
                new_population.append(self._mutate(c1))
                if len(new_population) < self.population_size:
                    new_population.append(self._mutate(c2))

            population = new_population[:self.population_size]

        result = OptimizationResult(
            best_params=best_params,
            best_fitness=best_fitness,
            generations_log=generations_log,
            all_evaluated=all_evaluated,
        )
        logger.info(f"寻优完成: best_fitness={best_fitness:.4f}")
        return result


# ═══════════════════════════════════════════
#  网格搜索（小参数空间备选）
# ═══════════════════════════════════════════

class GridSearch:
    """
    网格搜索：穷举所有参数组合。适合参数空间小（<500 组合）的场景。

    示例:
        grid = GridSearch(
            param_grid={
                "fast_period": [5, 10, 15, 20],
                "slow_period": [30, 50, 80],
                "leverage": [3, 5, 10],
            },
            fitness_fn=my_backtest_fn,
        )
        result = grid.run()
    """

    def __init__(self, param_grid: dict[str, list], fitness_fn: Callable[[dict], float]):
        self.param_grid = param_grid
        self.fitness_fn = fitness_fn

    def _generate_combinations(self) -> list[dict]:
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        combos = [{}]
        for key, vals in zip(keys, values):
            new_combos = []
            for combo in combos:
                for v in vals:
                    new_combo = copy.deepcopy(combo)
                    new_combo[key] = v
                    new_combos.append(new_combo)
            combos = new_combos
        return combos

    def run(self) -> OptimizationResult:
        combinations = self._generate_combinations()
        logger.info(f"网格搜索: {len(combinations)} 组参数组合")

        all_evaluated = []
        best_fitness = -float("inf")
        best_params = {}

        for i, params in enumerate(combinations):
            try:
                fitness = self.fitness_fn(params)
            except Exception as e:
                logger.warning(f"评估失败 [{i}]: {e}")
                fitness = -999.0

            all_evaluated.append((copy.deepcopy(params), float(fitness)))

            if fitness > best_fitness:
                best_fitness = fitness
                best_params = copy.deepcopy(params)

            if (i + 1) % 50 == 0:
                logger.info(f"  已评估 {i+1}/{len(combinations)}, 当前最优={best_fitness:.4f}")

        logger.info(f"网格搜索完成: best_fitness={best_fitness:.4f}")
        return OptimizationResult(
            best_params=best_params,
            best_fitness=best_fitness,
            all_evaluated=all_evaluated,
        )
