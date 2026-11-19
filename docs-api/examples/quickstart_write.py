import em

su = em.graph.node("SU002")
with em.write("Description of SU002") as tx:      # one act = one step of undo
    tx.update(su, "description", "Foundation of the colonnade, north side")

print(em.graph.node("SU002").description)
