"""Prototype AutoSolver framework for the delivery assignment challenge."""

from autosolver.agent import AgentDecision, AgentMemory, AgentReport, HeurAgenixLiteAgent
from autosolver.evaluator import Evaluator, Objective
from autosolver.features import InstanceFeatures, SolutionFeatures, extract_instance_features, extract_solution_features
from autosolver.generators import CASE_GENERATORS, STRESS_CASE_GENERATORS, generate_case
from autosolver.model import Assignment, BundleDiscount, Edge, Instance, Order, Rider
from autosolver.portfolio import PortfolioReport, PortfolioSolver

__all__ = [
    "Assignment",
    "AgentDecision",
    "AgentMemory",
    "AgentReport",
    "BundleDiscount",
    "CASE_GENERATORS",
    "Edge",
    "Evaluator",
    "HeurAgenixLiteAgent",
    "Instance",
    "InstanceFeatures",
    "Objective",
    "Order",
    "PortfolioReport",
    "PortfolioSolver",
    "Rider",
    "STRESS_CASE_GENERATORS",
    "SolutionFeatures",
    "extract_instance_features",
    "extract_solution_features",
    "generate_case",
]
