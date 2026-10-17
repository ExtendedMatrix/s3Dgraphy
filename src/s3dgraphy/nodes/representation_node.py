from .base_node import Node
from typing import Dict, Any, List, Optional, Union

class RepresentationNode(Node):
    """
    Base class for all representation nodes in 3D space.
    
    This class provides common functionality for RepresentationModelNode,
    RepresentationModelDocNode, and RepresentationModelSpecialFindNode.
    
    Attributes:
        node_type (str): Type of node, set by child classes
        type (str): The type of representation (e.g. "RM", "spatialized_image", "generic")
        transform (dict): Transformation data for positioning in 3D space, in
            the form of node datamodel 1.6.31 (geometry.transform)
    """
    
    # No node_type: this is the abstract family base, and the three concrete
    # subclasses declare their own. It used to declare "representation_node",
    # which made an abstract class authorable: a node serialised under that
    # name was built here, and since the node datamodel declares no entry for
    # RepresentationNode the RDF exporter found no mapping and emitted it with
    # no rdf:type. Nothing in the corpus ever used the name (checked
    # 2026-09-25), so removing it costs nothing and an unknown type now warns
    # on import instead of passing silently.
    
    def __init__(self, 
                 node_id: str,
                 name: str,
                 type: str = "generic",
                 transform: Optional[Dict[str, Any]] = None,
                 description: str = ""):
        """
        Initialize a new RepresentationNode.
        
        Args:
            node_id (str): Unique identifier for the node
            name (str): Name of the representation
            type (str): Type of representation
            transform (Dict[str, List[str]], optional): Transformation data with position, rotation, and scale
            description (str): Description of the representation
        """
        super().__init__(node_id=node_id, name=name, description=description)
        
        self.type = type
        
        # The transformation in the form of node datamodel 1.6.31 (E.D. 16-17
        # Oct 2026): numbers, degrees, rotation_order, up_axis. The identity
        # by default (until then: strings, radians, no axis). A transform
        # given is kept as given: the load of an em.json reads the old form
        # and says so (geometry.transform.migrate_graph_transforms).
        from ..geometry.transform import identity
        self.transform = identity() if transform is None else transform
        
        # Structure data for serialization
        self.data = {
            "transform": self.transform
        }
    
    def set_transform(self,
                      position: Optional[List[float]] = None,
                      rotation: Optional[List[float]] = None,
                      scale: Optional[List[float]] = None,
                      pivot: Optional[List[float]] = None,
                      rotation_order: Optional[str] = None,
                      up_axis: Optional[str] = None) -> None:
        """
        Set the transformation parameters, in the form of node datamodel
        1.6.31: numbers, the rotation in DEGREES (``rotation_order``, XYZ by
        default), the position in metres in the frame of the study, ``pivot``
        the point rotations and scales turn about (absent: the centre of the
        object's box). See :mod:`s3dgraphy.geometry.transform`.
        """
        from ..geometry.transform import write_form
        t = dict(self.transform or {})
        for key, value in (("position", position), ("rotation", rotation),
                           ("scale", scale), ("pivot", pivot),
                           ("rotation_order", rotation_order), ("up_axis", up_axis)):
            if value is not None:
                t[key] = value
        self.transform = write_form(t)
        self.data["transform"] = self.transform
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the node to a dictionary for JSON serialization.
        
        Returns:
            Dict[str, Any]: Dictionary representation of the node
        """
        return {
            self.node_id: {
                "type": self.type,
                "name": self.name,
                "description": self.description,
                "data": self.data
            }
        }


class RepresentationModelNode(RepresentationNode):
    """
    Node representing a 3D model or spatialized image.
    
    This class is used for general 3D models associated with stratigraphic units.
    
    Attributes:
        node_type (str): Type of node, set to "representation_model"
    """
    
    node_type = "representation_model"
    
    # Valid types of representation
    VALID_TYPES = {
        "RM": "Representation Model - 3D Model",
        "spatialized_image": "Spatialized Image",
        "generic": "Generic Representation"
    }
    
    def __init__(self, 
                 node_id: str,
                 name: str,
                 type: str = "RM",
                 transform: Optional[Dict[str, Any]] = None,
                 description: str = ""):
        """
        Initialize a new RepresentationModelNode.
        
        Args:
            node_id (str): Unique identifier for the node
            name (str): Name of the model
            type (str): Type of representation ("RM", "spatialized_image", or "generic")
            transform (Dict[str, List[str]], optional): Transformation data
            description (str): Description of the model
            
        Raises:
            ValueError: If the type is not valid
        """
        if type not in self.VALID_TYPES:
            raise ValueError(f"type must be one of: {list(self.VALID_TYPES.keys())}")
        
        super().__init__(
            node_id=node_id, 
            name=name, 
            type=type, 
            transform=transform,
            description=description
        )


class RepresentationModelDocNode(RepresentationNode):
    """
    Node representing a 3D model or spatialized image for documents.

    This class is used to instantiate documents, extractors or combiner nodes
    within the scene. An example is a historical photo positioned in its original position.

    Scope (Q-C, EM 1.6). The RMDoc is the RM of an asset that cannot sit in 3D
    without a transformation matrix — (0,0,0) is an improbable place for it —
    and that normally involves a POV / camera sighting the document (a section,
    an elevation, an image); typically a georeferenced 2D document used as a
    base. It is NOT the RMDoc case when a photogrammetric model is used as a
    SOURCE: that is an RM bound to its epoch, plus a Document. An asset already
    3D and already an RM does not generate an RMDoc. The family is a parallel of
    spatial instances of conceptual nodes::

        proxy : US  ::  RMSF : SF  ::  RM : state  ::  RMDoc : Document

    What has degrees here is the **spatialisation**, not the existence: the
    document certainly exists. Its metric authority of placement is graded on
    the ``geometry`` axis (``data["geometry"]``), whose vocabulary lives in
    ``em_visual_rules.json → document_variant_styles``::

        reality_based → observable → asserted → symbolic     (+ em_based, aside)

    That axis is authoritative HERE, on the spatial instance, not on the
    Document — which may mirror the value on its yEd border for diagram
    convenience but carries no position. Temporality is a separate matter: an
    attribution, certain or argued through a paradata chain, never a grade on
    this axis.

    Attributes:
        node_type (str): Type of node, set to "representation_model_doc"
    """
    
    node_type = "representation_model_doc"
    
    # Valid types of representation
    VALID_TYPES = {
        "RM": "Representation Model - 3D Model",
        "spatialized_image": "Spatialized Image",
        "generic": "Generic Representation"
    }
    
    def __init__(self, 
                 node_id: str,
                 name: str,
                 type: str = "spatialized_image",
                 transform: Optional[Dict[str, Any]] = None,
                 description: str = ""):
        """
        Initialize a new RepresentationModelDocNode.
        
        Args:
            node_id (str): Unique identifier for the node
            name (str): Name of the model
            type (str): Type of representation ("RM", "spatialized_image", or "generic")
            transform (Dict[str, List[str]], optional): Transformation data
            description (str): Description of the model
            
        Raises:
            ValueError: If the type is not valid
        """
        if type not in self.VALID_TYPES:
            raise ValueError(f"type must be one of: {list(self.VALID_TYPES.keys())}")
        
        super().__init__(
            node_id=node_id, 
            name=name, 
            type=type, 
            transform=transform,
            description=description
        )


class RepresentationModelSpecialFindNode(RepresentationNode):
    """
    Node representing a 3D model for special finds.
    
    This class is used to instantiate special finds in the scene. An example is
    a scanned 3D model of a capital repositioned in its original position
    according to an anastylosis hypothesis.
    
    Attributes:
        node_type (str): Type of node, set to "representation_model_sf"
    """
    
    node_type = "representation_model_sf"
    
    # Valid types of representation
    VALID_TYPES = {
        "RM": "Representation Model - 3D Model",
        "spatialized_image": "Spatialized Image",
        "generic": "Generic Representation"
    }
    
    def __init__(self, 
                 node_id: str,
                 name: str,
                 type: str = "RM",
                 transform: Optional[Dict[str, Any]] = None,
                 description: str = ""):
        """
        Initialize a new RepresentationModelSpecialFindNode.
        
        Args:
            node_id (str): Unique identifier for the node
            name (str): Name of the model
            type (str): Type of representation ("RM", "spatialized_image", or "generic")
            transform (Dict[str, List[str]], optional): Transformation data
            description (str): Description of the model
            
        Raises:
            ValueError: If the type is not valid
        """
        if type not in self.VALID_TYPES:
            raise ValueError(f"type must be one of: {list(self.VALID_TYPES.keys())}")
        
        super().__init__(
            node_id=node_id, 
            name=name, 
            type=type, 
            transform=transform,
            description=description
        )
