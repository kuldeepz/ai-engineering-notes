"""
Demonstrate ontology reasoning on a tiny family/kinship model.

The point of the demo: we assert only `hasParent` + gender, yet after running
an OWL reasoner the graph "knows" grandparents, ancestors, children, and who
counts as a Parent -- none of which were stated.

Run:  python reason.py
"""

from rdflib import Graph, Namespace, RDF
from rdflib.namespace import RDFS
import owlrl

FAM = Namespace("http://example.org/family#")


def load_graph(path: str = "family.ttl") -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def count_triples(g: Graph) -> int:
    return len(g)


def grandparent_query(g: Graph):
    """All inferred grandparent links."""
    q = """
        PREFIX : <http://example.org/family#>
        SELECT ?child ?grandparent WHERE { ?child :hasGrandparent ?grandparent . }
        ORDER BY ?child ?grandparent
    """
    return list(g.query(q))


def ancestor_query(g: Graph):
    """All inferred ancestor links (transitive closure of hasParent)."""
    q = """
        PREFIX : <http://example.org/family#>
        SELECT ?person ?ancestor WHERE { ?person :hasAncestor ?ancestor . }
        ORDER BY ?person ?ancestor
    """
    return list(g.query(q))


def parents_query(g: Graph):
    """Everyone the reasoner classified as a :Parent (never asserted)."""
    q = """
        PREFIX : <http://example.org/family#>
        SELECT DISTINCT ?p WHERE { ?p a :Parent . } ORDER BY ?p
    """
    return list(g.query(q))


def sibling_query(g: Graph):
    """Siblings = share a parent, computed at QUERY time (not stored)."""
    q = """
        PREFIX : <http://example.org/family#>
        SELECT DISTINCT ?a ?b WHERE {
            ?a :hasParent ?p .
            ?b :hasParent ?p .
            FILTER (?a != ?b)
        } ORDER BY ?a ?b
    """
    return list(g.query(q))


def short(term) -> str:
    return str(term).split("#")[-1]


def main() -> None:
    g = load_graph()
    before = count_triples(g)
    print(f"Asserted triples (before reasoning): {before}")
    print(f"  Grandparent links asserted: {len(grandparent_query(g))}")
    print(f"  Ancestor links asserted:    {len(ancestor_query(g))}")
    print(f"  Individuals typed :Parent:  {len(parents_query(g))}")

    # --- run the OWL-RL reasoner; it expands the graph in place ---
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)

    after = count_triples(g)
    print(f"\nReasoning complete. Triples now: {after}  (+{after - before} inferred)\n")

    print("Inferred GRANDPARENTS (child  ->  grandparent):")
    for child, gp in grandparent_query(g):
        print(f"  {short(child):8} ->  {short(gp)}")

    print("\nInferred ANCESTORS (person  ->  ancestor), incl. great-grandparents:")
    for person, anc in ancestor_query(g):
        print(f"  {short(person):8} ->  {short(anc)}")

    print("\nIndividuals the reasoner classified as :Parent:")
    for (p,) in parents_query(g):
        print(f"  {short(p)}")

    print("\nSiblings (derived at query time via SPARQL):")
    for a, b in sibling_query(g):
        print(f"  {short(a):8} <-> {short(b)}")


if __name__ == "__main__":
    main()
