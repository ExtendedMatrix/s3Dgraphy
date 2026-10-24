"""The library's own IRIs live under the REGISTERED space w3id.org/extendedmatrix
(MICRO specifica em.json, 24 Oct 2026); the unregistered w3id.org/em/s3dgraphy#
they were minted under before is read as an alias. The ontology IRI
(w3id.org/em/ontology) is NOT changed: it is already in the delivered RDF."""
from s3dgraphy.exporter.rdf_exporter import EM, S3D, S3D_LEGACY
from s3dgraphy.geometry import wkt


def test_minted_terms_are_under_extendedmatrix():
    assert str(S3D) == "https://w3id.org/extendedmatrix/s3dgraphy#"
    assert [str(ns) for ns in S3D_LEGACY] == ["https://w3id.org/em/s3dgraphy#"]
    assert str(EM) == "https://w3id.org/em/ontology#"          # unchanged


def test_a_minted_crs_is_written_new_and_read_old_and_new():
    iri = wkt.crs_iri("Stereo 70 local shift")
    assert iri.startswith("https://w3id.org/extendedmatrix/s3dgraphy#crs_")
    assert wkt.crs_of_iri(iri) == "Stereo_70_local_shift"
    old = "https://w3id.org/em/s3dgraphy#crs_Stereo_70_local_shift"
    assert wkt.crs_of_iri(old) == "Stereo_70_local_shift"
    assert wkt.crs_iri("EPSG:3844") == "http://www.opengis.net/def/crs/EPSG/0/3844"
