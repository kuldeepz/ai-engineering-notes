"""
Tests for the family ontology demo.

These verify the TWO things that matter:
  1. The asserted graph does NOT already contain the derived facts.
  2. After reasoning, the expected facts ARE entailed.

Run:  pytest -v        (after `pip install -r requirements.txt pytest`)
"""

import owlrl
import pytest
from rdflib import Namespace

import reason

FAM = Namespace("http://example.org/family#")


@pytest.fixture
def asserted():
    """The graph as authored, BEFORE reasoning."""
    return reason.load_graph("family.ttl")


@pytest.fixture
def inferred(asserted):
    """The same graph AFTER the OWL-RL reasoner has expanded it."""
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(asserted)
    return asserted


# --- baseline: derived facts must NOT be asserted up front -------------------

def test_no_grandparents_before_reasoning(asserted):
    assert len(reason.grandparent_query(asserted)) == 0


def test_no_parents_typed_before_reasoning(asserted):
    assert len(reason.parents_query(asserted)) == 0


# --- entailments: facts that must appear AFTER reasoning ---------------------

def test_grandparents_inferred(inferred):
    pairs = {(reason.short(c), reason.short(g)) for c, g in reason.grandparent_query(inferred)}
    assert ("Eve", "Alice") in pairs
    assert ("Eve", "Bob") in pairs
    assert ("Frank", "Alice") in pairs
    assert ("Frank", "Bob") in pairs


def test_ancestor_is_transitive(inferred):
    pairs = {(reason.short(p), reason.short(a)) for p, a in reason.ancestor_query(inferred)}
    # Eve -> Carol -> Alice, so Alice must be an ancestor of Eve (transitivity).
    assert ("Eve", "Carol") in pairs
    assert ("Eve", "Alice") in pairs


def test_parent_class_inferred(inferred):
    parents = {reason.short(p) for (p,) in reason.parents_query(inferred)}
    assert parents == {"Alice", "Bob", "Carol"}


def test_inverse_property_gives_children(inferred):
    # hasChild is the inverse of hasParent; Alice should have Carol as a child.
    assert (FAM.Alice, FAM.hasChild, FAM.Carol) in inferred


def test_siblings_from_shared_parent(inferred):
    pairs = {(reason.short(a), reason.short(b)) for a, b in reason.sibling_query(inferred)}
    assert ("Eve", "Frank") in pairs
    assert ("Carol", "Dave") in pairs


def test_reasoning_grows_the_graph(asserted):
    before = len(asserted)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(asserted)
    assert len(asserted) > before
