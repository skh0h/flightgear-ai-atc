"""
Taxi graph and A* routing from gate to runway.

TODO: Implement:
  - build_graph(airport_picture) -> networkx.Graph (or plain adjacency dict)
  - find_route(graph, start_node, end_node) -> list[int] (node indices)
    using A* with haversine heuristic
  - route_to_instructions(route, airport_picture) -> list[str]
    converting node list to human-readable taxi instructions
"""
