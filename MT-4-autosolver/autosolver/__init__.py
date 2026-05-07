"""Prototype AutoSolver framework for the delivery assignment challenge."""

from autosolver.agent import AgentDecision, AgentMemory, AgentReport, HeurAgenixLiteAgent
from autosolver.algorithm_generation import (
    AlgorithmGenerator,
    OpenAICompatibleAlgorithmGenerator,
    TemplateAlgorithmGenerator,
    make_algorithm_generator,
    parse_specs,
)
from autosolver.evaluator import Evaluator, Objective
from autosolver.features import InstanceFeatures, SolutionFeatures, extract_instance_features, extract_solution_features
from autosolver.generated_solver import GeneratedGreedySolver, HeuristicSpec
from autosolver.generators import CASE_GENERATORS, STRESS_CASE_GENERATORS, generate_case
from autosolver.model import Assignment, BundleDiscount, Edge, Instance, Order, Rider
from autosolver.official import (
    OfficialAssignment,
    OfficialCandidate,
    OfficialEvaluator,
    OfficialInstance,
    OfficialOffer,
    OfficialPortfolioSolver,
    OfficialReport,
    parse_official_input,
)
from autosolver.portfolio import PortfolioReport, PortfolioSolver

__all__ = [
    "Assignment",
    "AgentDecision",
    "AgentMemory",
    "AgentReport",
    "AlgorithmGenerator",
    "BundleDiscount",
    "CASE_GENERATORS",
    "Edge",
    "Evaluator",
    "GeneratedGreedySolver",
    "HeurAgenixLiteAgent",
    "HeuristicSpec",
    "Instance",
    "InstanceFeatures",
    "Objective",
    "OfficialAssignment",
    "OfficialCandidate",
    "OfficialEvaluator",
    "OfficialInstance",
    "OfficialOffer",
    "OfficialPortfolioSolver",
    "OfficialReport",
    "OpenAICompatibleAlgorithmGenerator",
    "Order",
    "PortfolioReport",
    "PortfolioSolver",
    "Rider",
    "STRESS_CASE_GENERATORS",
    "SolutionFeatures",
    "TemplateAlgorithmGenerator",
    "extract_instance_features",
    "extract_solution_features",
    "generate_case",
    "make_algorithm_generator",
    "parse_official_input",
    "parse_specs",
]
