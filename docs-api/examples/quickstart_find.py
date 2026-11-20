import em
from collections import Counter

units = list(em.graph.nodes(type="US"))  # every stratigraphic unit
print(len(units), "units:", ", ".join(u.name for u in units))

kinds = Counter(n.type for n in em.graph.nodes())
print(kinds.most_common(5))              # what the study is made of
