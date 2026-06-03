"""
Rule-based atomic tagger — no external AI API, pure Python dictionary matching.

Tags are organized in 3 groups:
  Domain  : application area (manufacturing, logistics, …)
  Method  : technical approach (digital_twin, llm, rag, …)
  Problem : task type (scheduling, routing, anomaly_detection, …)

Usage:
    from tagger.atomic_tagger import tag_paper
    tags = tag_paper(paper)   # returns list[str]
    paper["tags"] = tags
"""

# ── Rule dictionary ───────────────────────────────────────────────────────────
# Each entry: (group_prefix, tag_name, keywords_that_trigger_the_tag)
# Match is case-insensitive substring search on title + abstract.

GROUPS: list[tuple[str, str, list[str]]] = [
    # ── Domain ────────────────────────────────────────────────────────────────
    ("domain", "manufacturing", [
        "manufacturing", "factory", "production", "assembly", "shop floor",
        "machining", "fabrication", "industrial process", "smart factory",
        "industry 4.0", "industry 5.0",
    ]),
    ("domain", "logistics", [
        "logistics", "supply chain", "warehouse", "inventory", "freight",
        "delivery", "distribution", "last-mile", "last mile",
    ]),
    ("domain", "transportation", [
        "transportation", "traffic", "vehicle routing", "autonomous driving",
        "fleet management", "autonomous vehicle", "self-driving", "mobility",
    ]),
    ("domain", "healthcare", [
        "healthcare", "medical", "clinical", "hospital", "patient",
        "diagnosis", "treatment", "disease", "health informatics", "biomedical",
    ]),
    ("domain", "education", [
        "education", "e-learning", "elearning", "teaching", "student",
        "curriculum", "learning management", "tutoring",
    ]),
    ("domain", "ecommerce", [
        "e-commerce", "ecommerce", "retail", "shopping", "recommendation",
        "purchase", "marketplace", "online store",
    ]),
    ("domain", "robotics", [
        "robot", "robotics", "drone", "manipulation", "gripper",
        "autonomous robot", "uav", "unmanned aerial",
    ]),

    # ── Method ────────────────────────────────────────────────────────────────
    ("method", "digital_twin", [
        "digital twin", "digital-twin", "cyber-physical", "virtual model",
        "virtual replica", "digital shadow",
    ]),
    ("method", "multi_agent", [
        "multi-agent", "multiagent", "multi agent", "agent-based",
        "swarm intelligence", "swarm agent",
    ]),
    ("method", "llm", [
        "large language model", "llm", "gpt-", "chatgpt", "gemini",
        "transformer-based", "language model", "foundation model",
        "pre-trained model", "pretrained language",
    ]),
    ("method", "rag", [
        "retrieval-augmented", "retrieval augmented", "rag",
        "retrieval-based generation", "knowledge retrieval",
    ]),
    ("method", "reinforcement_learning", [
        "reinforcement learning", "deep reinforcement", "q-learning",
        "policy gradient", "dqn", "ppo", "actor-critic",
        "markov decision process", "mdp",
    ]),
    ("method", "simulation", [
        "simulation", "simulator", "simulated environment",
        "monte carlo", "discrete event simulation", "agent-based simulation",
    ]),
    ("method", "optimization", [
        "optimization", "optimisation", "genetic algorithm",
        "evolutionary algorithm", "particle swarm", "heuristic",
        "metaheuristic", "combinatorial optimization", "integer programming",
    ]),

    # ── Problem ───────────────────────────────────────────────────────────────
    ("problem", "scheduling", [
        "scheduling", "task allocation", "job shop", "timetabling", "makespan",
        "workflow scheduling",
    ]),
    ("problem", "routing", [
        "routing", "path planning", "path finding", "route optimization",
        "travelling salesman", "vehicle route",
    ]),
    ("problem", "planning", [
        "task planning", "goal-directed", "hierarchical planning",
        "automated planning", "motion planning",
    ]),
    ("problem", "resource_allocation", [
        "resource allocation", "resource management", "capacity planning",
        "load balancing", "assignment problem", "resource scheduling",
    ]),
    ("problem", "decision_making", [
        "decision making", "decision support", "multi-criteria",
        "uncertainty", "risk assessment", "decision tree",
    ]),
    ("problem", "anomaly_detection", [
        "anomaly detection", "fault detection", "outlier detection",
        "intrusion detection", "defect detection", "predictive maintenance",
    ]),
]


def tag_paper(paper: dict) -> list[str]:
    """
    Match paper against rule dictionary and return a list of atomic tag strings.
    Tag format: "domain:manufacturing", "method:rag", "problem:scheduling", etc.
    """
    text = " ".join([
        paper.get("title", ""),
        paper.get("summary", ""),
        " ".join(paper.get("keywords", [])),
    ]).lower()

    tags: list[str] = []
    for group, name, keywords in GROUPS:
        if any(kw in text for kw in keywords):
            tags.append(f"{group}:{name}")

    return tags
