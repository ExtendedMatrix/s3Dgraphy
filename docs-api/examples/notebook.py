import os
import em

os.environ["S3DGRAPHY_AUTHOR"] = "https://orcid.org/0000-0002-1825-0097"  # who writes
em.open(os.environ.get("EM_FILE", "templu-mare.em.json"))
with em.write("Description of SU002") as tx:
    tx.update("SU002", "description", "Foundation of the colonnade")
print(em.graph.node("SU002").description)
em.save(os.environ.get("EM_OUT", "templu-mare-new.em.json"))
