"""GCPSetNode + RegistrationTransformNode — how a model got into the world.

A photogrammetric model comes out of the engine in *some* frame. Which frame,
and by what right, is not a property of the mesh: it is a **measurement** and a
**solution**, and both are facts somebody made and somebody else may have to
check. So they are nodes, not fields on the model.

Two classes, because they answer two different questions and fail in two
different ways:

* :class:`GCPSetNode` — the CONTROL: for each point, where it was seen (which
  photograph, which pixel) and where it is in the world (coordinates + CRS +
  uncertainty). This is the *evidence*. It can exist before any model does, and
  it survives being re-used by a second reconstruction.
* :class:`RegistrationTransformNode` — the SOLUTION: the 7-parameter similarity
  (rotation, translation, scale) that the bundle adjustment settled on, with its
  residuals. This is what the model is placed by, and it is the thing that gets
  REPLACED when better coordinates arrive — the old one staying in the graph,
  historicised, because "we moved it in March" is provenance.

**The two modes the design turns on** (EM_design_photogrammetry-pipeline §5) are
visible in the graph's SHAPE, not in a flag somebody has to read:

* **absolute** — a GCP set with known world coordinates → a transform that
  ``has_gcp_set`` points at. Registered, and you can see what registered it.
* **local** — a LiDAR/scale-bar prior only → a transform with ``scale`` solved
  and no GCP set, and ``crs`` left None. Scaled and oriented in a site-local
  frame, *honestly not georeferenced*. Re-registering later is a NEW process
  producing a NEW transform, never an edit of this one.

A model with no transform at all is a model nobody placed. That is also a true
sentence, and the absence says it.
"""

from typing import Any, Dict, List, Optional

from .base_node import Node


class GeoreferencingError(ValueError):
    """A control set or a transform that would be a lie if it were stored."""


class GCPSetNode(Node):
    """The ground control points a registration was (or will be) solved from.

    ``points`` is a list of dicts, one per control point::

        {"id": "gcp01",
         "world": [x, y, z],            # in `crs`
         "observations": [{"image": "IMG_0042.JPG", "pixel": [1234.5, 987.0]}],
         "uncertainty": 0.012}          # metres, optional

    Validated on construction, and the validation is the point: a control point
    with no world coordinate is not a control point, and a set of two is not a
    set the bundle can solve (three non-collinear is the minimum the design
    states). Both are refused HERE rather than discovered by an engine an hour
    into a job.

    ``crs`` may be ``None`` — that is the honest value for a site-local grid
    whose EPSG code does not exist. It is not the same as absent: a caller that
    means WGS84 says so.

    ``control`` says WHAT the points are (dev30, E.D. 2 Oct 2026, D7):
    ``ground_control_points`` (the default — surveyed places seen in the
    photographs) or ``camera_positions`` — the GPS positions of the cameras
    themselves, each point a photograph (``image``) with no pixel observation,
    because the camera is where the photograph was taken from, not something
    seen in it. A set of camera positions is a weaker control than ground
    control (a drone's GPS can be tens of metres off), and it is said, never
    hidden: ``accuracy_m`` is the accuracy the project records for the cameras,
    and ``validate`` warns «georeferenced only by camera GPS». It is solvable
    with three positions.
    """

    node_type = "gcp_set"

    #: below this a similarity is not determined — three non-collinear points
    MINIMUM_POINTS = 3

    #: what the points of a set are (D7, dev30)
    GROUND_CONTROL = "ground_control_points"
    CAMERA_POSITIONS = "camera_positions"
    CONTROLS = (GROUND_CONTROL, CAMERA_POSITIONS)

    def __init__(self, node_id: str, name: str = "Ground control points",
                 points: Optional[List[Dict[str, Any]]] = None,
                 crs: Optional[str] = None,
                 description: str = "",
                 data: Optional[Dict[str, Any]] = None,
                 control: Optional[str] = None,
                 accuracy_m: Optional[float] = None):
        super().__init__(node_id=node_id, name=name, description=description)
        self.data = dict(data or {})
        control = control or self.data.get("control") or self.GROUND_CONTROL
        if control not in self.CONTROLS:
            raise GeoreferencingError(
                f"control {control!r}: a set is {self.GROUND_CONTROL} or "
                f"{self.CAMERA_POSITIONS}")
        self.control = control
        if control != self.GROUND_CONTROL:
            self.data["control"] = control
        if accuracy_m is None:
            accuracy_m = self.data.get("accuracy_m")
        if accuracy_m is not None:
            self.data["accuracy_m"] = float(accuracy_m)
        self.points = self._validate(points or [])
        self.crs = crs.strip() if isinstance(crs, str) and crs.strip() else None
        self.data["points"] = self.points
        self.data["crs"] = self.crs

    @staticmethod
    def _validate(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean: List[Dict[str, Any]] = []
        for index, raw in enumerate(points):
            if not isinstance(raw, dict):
                raise GeoreferencingError(
                    f"control point {index} is a {type(raw).__name__}, not a "
                    f"record: a GCP is an id, a place and where it was seen")
            pid = str(raw.get("id") or "").strip()
            if not pid:
                raise GeoreferencingError(
                    f"control point {index} has no id: two points nobody can "
                    f"tell apart cannot be matched to their observations")
            world = raw.get("world")
            if (not isinstance(world, (list, tuple)) or len(world) != 3
                    or not all(isinstance(c, (int, float)) for c in world)):
                raise GeoreferencingError(
                    f"control point {pid!r} has no world coordinate [x, y, z]: "
                    f"a point without one controls nothing")
            observations = raw.get("observations") or []
            for obs in observations:
                if not isinstance(obs, dict) or not str(obs.get("image") or "").strip():
                    raise GeoreferencingError(
                        f"an observation of {pid!r} names no image: a pixel "
                        f"without a photograph cannot be re-measured")
                pixel = obs.get("pixel")
                if (not isinstance(pixel, (list, tuple)) or len(pixel) != 2
                        or not all(isinstance(c, (int, float)) for c in pixel)):
                    raise GeoreferencingError(
                        f"an observation of {pid!r} on {obs.get('image')!r} has "
                        f"no [x, y] pixel")
            entry: Dict[str, Any] = {"id": pid, "world": [float(c) for c in world],
                     "observations": [
                         {"image": str(o["image"]).strip(),
                          "pixel": [float(o["pixel"][0]), float(o["pixel"][1])]}
                         for o in observations]}
            if raw.get("uncertainty") is not None:
                entry["uncertainty"] = float(raw["uncertainty"])
            if str(raw.get("image") or "").strip():
                # a camera position: the photograph it is the position OF
                entry["image"] = str(raw["image"]).strip()
            clean.append(entry)
        return clean

    @property
    def solvable(self) -> bool:
        """Enough points, each seen at least once, for a similarity to exist.

        Reported, never enforced at construction: a set being assembled in the
        field is incomplete for a while, and refusing to store it would be
        refusing the working state. The RUNNER is where it becomes a refusal.
        """
        if self.control == self.CAMERA_POSITIONS:
            # each camera is its own observation: where the photograph was
            # taken from
            return len(self.points) >= self.MINIMUM_POINTS
        seen = [p for p in self.points if p.get("observations")]
        return len(seen) >= self.MINIMUM_POINTS

    def gcp_list(self, *, crs: Optional[str] = None) -> str:
        """The set as ODM's ``gcp_list.txt`` — the one format the engine reads.

        First line is the CRS (a proj string or ``EPSG:xxxx``); each following
        line is ``x y z pixel_x pixel_y image_name [gcp_label]``. Generated from
        the same payload the graph holds, so the file an engine saw and the
        record a reader sees cannot drift.
        """
        header = crs or self.crs
        if not header:
            raise GeoreferencingError(
                "a gcp_list.txt needs a CRS on its first line: this set has "
                "none, which means it is a local grid — pass one explicitly if "
                "the engine should treat it as absolute")
        lines = [header]
        for point in self.points:
            x, y, z = point["world"]
            for obs in point["observations"]:
                px, py = obs["pixel"]
                lines.append(f"{x} {y} {z} {px} {py} {obs['image']} {point['id']}")
        return "\n".join(lines) + "\n"

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.node_id, "type": self.node_type, "name": self.name,
                "description": self.description, "data": self.data}


class RegistrationTransformNode(Node):
    """The similarity that places a model — 7 parameters and what they cost.

    ``rotation`` is a 3×3 row-major matrix, ``translation`` an [x, y, z],
    ``scale`` a positive float. ``rms`` and ``residuals`` are the quality of the
    fit: a transform without them is a claim without an error bar, which is why
    they are stored beside it rather than in a log file nobody keeps.

    ``crs`` is the frame the model lands IN. ``None`` means a site-local frame —
    the mode (b) of the design — and that is a different sentence from "we do
    not know", which is what an absent transform says.
    """

    node_type = "registration_transform"

    def __init__(self, node_id: str, name: str = "Registration",
                 rotation: Optional[List[List[float]]] = None,
                 translation: Optional[List[float]] = None,
                 scale: float = 1.0,
                 crs: Optional[str] = None,
                 rms: Optional[float] = None,
                 residuals: Optional[Dict[str, float]] = None,
                 description: str = "",
                 data: Optional[Dict[str, Any]] = None):
        super().__init__(node_id=node_id, name=name, description=description)
        self.data = dict(data or {})
        self.rotation = self._identity() if rotation is None else self._rotation(rotation)
        self.translation = ([0.0, 0.0, 0.0] if translation is None
                            else self._vector(translation))
        if not isinstance(scale, (int, float)) or scale <= 0:
            raise GeoreferencingError(
                f"scale must be a positive number, got {scale!r}: a similarity "
                f"with zero or negative scale collapses or mirrors the model")
        self.scale = float(scale)
        self.crs = crs.strip() if isinstance(crs, str) and crs.strip() else None
        self.rms = float(rms) if rms is not None else None
        self.residuals = {str(k): float(v) for k, v in (residuals or {}).items()}
        self.data.update({"rotation": self.rotation, "translation": self.translation,
                          "scale": self.scale, "crs": self.crs, "rms": self.rms,
                          "residuals": self.residuals})

    @staticmethod
    def _identity() -> List[List[float]]:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

    @staticmethod
    def _rotation(raw: Any) -> List[List[float]]:
        if (not isinstance(raw, (list, tuple)) or len(raw) != 3
                or any(not isinstance(r, (list, tuple)) or len(r) != 3 for r in raw)):
            raise GeoreferencingError(
                "rotation must be a 3x3 row-major matrix: anything else is not "
                "a rotation a consumer could apply")
        return [[float(c) for c in row] for row in raw]

    @staticmethod
    def _vector(raw: Any) -> List[float]:
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            raise GeoreferencingError("translation must be [x, y, z]")
        return [float(c) for c in raw]

    @property
    def georeferenced(self) -> bool:
        """True only when this transform lands the model in a NAMED frame.

        The one question a consumer actually asks before assembling two models
        without aligning them by hand — and the reason mode (b) must not be
        allowed to look like mode (a).
        """
        return self.crs is not None

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.node_id, "type": self.node_type, "name": self.name,
                "description": self.description, "data": self.data}
