import em

print(em.graph)                          # the graph of the open study

su = em.graph.node("SU002")              # a unit, by its name (or its id)
print(su.name, "—", su.description)

for edge in su.edges():                  # what it is connected to
    print(" ", edge.type, "→", edge.target.name)
