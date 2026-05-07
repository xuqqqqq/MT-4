"""Command line entrypoint for generated cases and JSON instances."""

from __future__ import annotations

import argparse
import json
import sys

from autosolver.agent import AgentMemory, HeurAgenixLiteAgent
from autosolver.algorithm_generation import make_algorithm_generator
from autosolver.generators import CASE_GENERATORS, STRESS_CASE_GENERATORS, generate_case, random_case
from autosolver.io import assignment_to_dict, read_instance, write_assignment, write_instance
from autosolver.portfolio import PortfolioSolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prototype delivery AutoSolver")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--case", choices=sorted(CASE_GENERATORS), help="run a built-in synthetic case")
    source.add_argument("--stress-case", choices=sorted(STRESS_CASE_GENERATORS), help="run a larger stress case")
    source.add_argument("--input", help="read an internal JSON instance")
    parser.add_argument("--list-cases", action="store_true", help="list available synthetic cases")
    parser.add_argument("--list-stress-cases", action="store_true", help="list available larger stress cases")
    parser.add_argument("--dump-case", help="write the selected/generated instance JSON to this path")
    parser.add_argument("--output", help="write best assignment JSON to this path")
    parser.add_argument("--time-limit", type=float, default=9.0, help="portfolio time limit in seconds")
    parser.add_argument("--agent", action="store_true", help="use the HeurAgenix-lite state-aware selector")
    parser.add_argument("--agent-history", help="append agent decisions to this JSONL file")
    parser.add_argument(
        "--generate-algorithms",
        type=int,
        default=0,
        metavar="N",
        help="ask the agent to generate N bounded heuristic specs before solving",
    )
    parser.add_argument(
        "--algorithm-generator",
        choices=("template", "openai-compatible"),
        default="template",
        help="generation backend; template is deterministic, openai-compatible calls an external API",
    )
    parser.add_argument("--llm-endpoint", default="https://api.openai.com/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--llm-model", help="model name for openai-compatible algorithm generation")
    parser.add_argument("--llm-api-key-env", default="AUTOSOLVER_LLM_API_KEY", help="environment variable holding the API key")
    parser.add_argument("--llm-timeout", type=float, default=20.0, help="algorithm generation API timeout in seconds")
    parser.add_argument("--print-generated-specs", action="store_true", help="print generated heuristic specs in text mode")
    parser.add_argument("--random", action="store_true", help="use a generated random instance")
    parser.add_argument("--seed", type=int, default=0, help="random instance seed")
    parser.add_argument("--orders", type=int, default=30, help="random instance order count")
    parser.add_argument("--riders", type=int, default=8, help="random instance rider count")
    parser.add_argument("--json", action="store_true", help="print machine-readable report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_cases:
        for name in sorted(CASE_GENERATORS):
            print(name)
        return 0

    if args.list_stress_cases:
        for name in sorted(STRESS_CASE_GENERATORS):
            print(name)
        return 0

    if args.input:
        instance = read_instance(args.input)
    elif args.random:
        instance = random_case(seed=args.seed, order_count=args.orders, rider_count=args.riders)
    elif args.stress_case:
        instance = generate_case(args.stress_case)
    else:
        instance = generate_case(args.case or "tiny_manual")

    if args.dump_case:
        write_instance(instance, args.dump_case)

    agent_report = None
    if args.agent:
        algorithm_generator = None
        if args.generate_algorithms > 0:
            algorithm_generator = make_algorithm_generator(
                provider=args.algorithm_generator,
                endpoint=args.llm_endpoint,
                model=args.llm_model,
                api_key_env=args.llm_api_key_env,
                timeout_sec=args.llm_timeout,
            )
        agent_report = HeurAgenixLiteAgent(
            time_limit_sec=args.time_limit,
            memory=AgentMemory(args.agent_history),
            algorithm_generator=algorithm_generator,
            generated_count=args.generate_algorithms,
        ).solve(instance)
        report = agent_report.portfolio
    else:
        if args.generate_algorithms > 0:
            parser.error("--generate-algorithms requires --agent")
        report = PortfolioSolver(time_limit_sec=args.time_limit).solve(instance)

    if args.output:
        write_assignment(report.assignment, args.output)

    if args.json:
        payload = {
            "instance": instance.name,
            "best_solver": report.best_solver,
            "elapsed_sec": report.elapsed_sec,
            "objective": {
                "expected_accepted": report.objective.expected_accepted,
                "total_cost": report.objective.total_cost,
                "offer_count": report.objective.offer_count,
                "feasible": report.objective.feasible,
                "violations": list(report.objective.violations),
            },
            "runs": [
                {
                    "solver": run.solver_name,
                    "elapsed_sec": run.elapsed_sec,
                    "objective": None
                    if run.objective is None
                    else {
                        "expected_accepted": run.objective.expected_accepted,
                        "total_cost": run.objective.total_cost,
                        "offer_count": run.objective.offer_count,
                        "feasible": run.objective.feasible,
                    },
                    "error": run.error,
                }
                for run in report.runs
            ],
            "assignment": assignment_to_dict(report.assignment),
        }
        if agent_report is not None:
            payload["agent"] = {
                "selected_solvers": list(agent_report.decision.selected_solvers),
                "scenario_tags": list(agent_report.decision.scenario_tags),
                "rationale": list(agent_report.decision.rationale),
                "features": agent_report.decision.features.to_dict(),
                "generated_specs": [spec.to_dict() for spec in agent_report.decision.generated_specs],
            }
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print(f"instance: {instance.name}")
        if agent_report is not None:
            print(f"agent_tags: {', '.join(agent_report.decision.scenario_tags) or 'none'}")
            print(f"agent_selected: {', '.join(agent_report.decision.selected_solvers)}")
            if args.print_generated_specs and agent_report.decision.generated_specs:
                print("generated_specs:")
                for spec in agent_report.decision.generated_specs:
                    print(f"- {spec.name}: {json.dumps(spec.to_dict(), ensure_ascii=False)}")
        print(f"best_solver: {report.best_solver}")
        print(f"elapsed_sec: {report.elapsed_sec:.4f}")
        print(f"objective: {report.objective.label()}")
        for run in report.runs:
            if run.error:
                print(f"- {run.solver_name}: ERROR after {run.elapsed_sec:.4f}s: {run.error}")
            elif run.objective:
                print(f"- {run.solver_name}: {run.objective.label()} in {run.elapsed_sec:.4f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
