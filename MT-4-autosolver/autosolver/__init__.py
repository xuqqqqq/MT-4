"""Prototype AutoSolver framework for the delivery assignment challenge."""

from autosolver.evaluator import Evaluator, Objective
from autosolver.generators import CASE_GENERATORS, generate_case
from autosolver.model import Assignment, BundleDiscount, Edge, Instance, Order, Rider
from autosolver.portfolio import PortfolioReport, PortfolioSolver

__all__ = [
    "Assignment",
    "BundleDiscount",
    "CASE_GENERATORS",
    "Edge",
    "Evaluator",
    "Instance",
    "Objective",
    "Order",
    "PortfolioReport",
    "PortfolioSolver",
    "Rider",
    "generate_case",
]
