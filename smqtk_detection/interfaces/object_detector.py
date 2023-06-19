import abc
import hashlib

import numpy

from typing import Optional, Hashable, Set, Iterator, Dict, Tuple, Any, Type, TypeVar

from smqtk_core import Plugfigurable
from smqtk_image_io.interfaces.image_reader import ImageReader
from smqtk_dataprovider import ContentTypeValidator
from smqtk_core.configuration import (
    make_default_config,
    from_config_dict,
    to_config_dict
)

from smqtk_classifier._defaults import DFLT_CLASSIFIER_FACTORY
from smqtk_detection._defaults import DFLT_DETECTION_FACTORY

from smqtk_image_io import AxisAlignedBoundingBox
from smqtk_detection.interfaces.detection_element import DetectionElement
from smqtk_detection.detection_element_factory \
    import DetectionElementFactory
from smqtk_dataprovider.interfaces.data_element import DataElement
from smqtk_classifier.classification_element_factory import ClassificationElementFactory

ImMatObDet = TypeVar("ImMatObDet", bound="ImageMatrixObjectDetector")


class ObjectDetector (Plugfigurable, ContentTypeValidator, metaclass=abc.ABCMeta):
    """
    Abstract interface to an object detection algorithm.

    An object detection algorithm is one that can take in data and output zero
    or more detection elements, where each detection represents a spatial
    region in the data.

    This high level interface only requires detection element returns (spatial
    bounding-boxes with associated classification elements).
    """

    __slots__ = ()

    @staticmethod
    def _gen_detection_uuid(data_uuid: str, bbox: AxisAlignedBoundingBox, labels: Any) -> Hashable:
        """
        Local standard for producing the UUID of a DetectionElement based on
        parent data, component bounding box and classification labels.

        :param str data_uuid:
            UUID of parent data element (checksum hash string) this detection
            is derived from.
        :param smqtk.representation.AxisAlignedBoundingBox bbox:
            Detection bounding box instance.
        :param labels:
            Sequence of string classification labels.

        :return: Detection UUID string that is the SHA1 checksum of the
            component data.

        """
        # noinspection PyStringFormat
        # - uses variadic expansion which fools current linter.
        hashable = data_uuid + \
            '{}{}{}{}'.format(*(bbox.min_vertex.tolist() +
                                bbox.max_vertex.tolist())) + \
            ''.join(sorted(map(str, labels)))
        return hashlib.sha1(bytes(hashable, "utf8")).hexdigest()

    def detect_objects(
            self,
            data_element: DataElement,
            de_factory: DetectionElementFactory = DFLT_DETECTION_FACTORY,
            ce_factory: ClassificationElementFactory = DFLT_CLASSIFIER_FACTORY
    ) -> Optional[Iterator[DetectionElement]]:
        """
        Detect objects in the given data.

        UUIDs of detections are based on the hash produced from the combination
        of:

        - Detection bounding-box bounding coordinates

        - Classification label set predicted for a bounding box.

        :param smqtk.representation.DataElement data_element:
            Source data from which to detect objects within.
        :param smqtk.representation.DetectionElementFactory de_factory:
            Factory for generating DetectionElement instances. The default
            factory yields MemoryClassificationElement instances.
        :param smqtk.representation.ClassificationElementFactory ce_factory:
            Factory for generating ClassificationElement instances for
            detections. The default factory yields MemoryClassificationElement
            instances.

        :raises ValueError: Given data element content was not of a valid
            content type that this class reports as valid for object detection.

        :return: Iterator over result DetectionElement instances as generated
            by the given DetectionElementFactory, containing classification
            elements as generated by the given ClassificationElementFactory.
        :rtype: collections.abc.Iterable[smqtk.representation.DetectionElement]

        """
        self.raise_valid_element(data_element)

        # We know that the UUID of a DataElement should be a checksum of sorts,
        # so we can generally assume a string-cast is unique preserving.
        de_uuid = str(data_element.uuid())

        type_str = 'object detection classification'
        dets = self._detect_objects(data_element)
        if dets is None:
            return None
        for bbox, c_map in dets:
            # Determine UUID of detection from bbox and classification labels
            det_uuid = self._gen_detection_uuid(de_uuid, bbox, c_map.keys())

            ce = ce_factory.new_classification(type_str, det_uuid)
            ce.set_classification(c_map)

            de = de_factory.new_detection(det_uuid).set_detection(bbox, ce)
            yield de

    @abc.abstractmethod
    def _detect_objects(
            self,
            data: DataElement
    ) -> Optional[Iterator[Tuple[AxisAlignedBoundingBox, Dict[Hashable, float]]]]:
        """
        Internal method that defines the generation of paired bounding boxes
        and classification maps for detected objects in the given data.

        :param smqtk.representation.DataElement data:
            Source data (DataElement) from which to detect objects within.

        :return: Iterable over paired ``AxisAlignedBoundingBox`` and
            classification map for detected objects. The returned
            "classification map" should follow the format described by
            ``smqtk.representation.ClassificationElement``: dictionary where
            keys are classification labels and values are classification
            probabilities.
        :rtype:
            collections.abc.Iterator[(smqtk.representation.AxisAlignedBoundingBox,
                                      dict[collections.abc.Hashable, float])]

        """


class ImageMatrixObjectDetector (ObjectDetector, metaclass=abc.ABCMeta):
    """
    Class of object detectors that operate over the pixel matrix of an image.

    This sub abstract class standardizes the use of an
    :class:`smqtk.algorithms.ImageReader` algorithm to read an image file's
    pixels as well as determine which image formats are valid input elements.
    There is a special exception of :class:`.MatrixDataElement` types as they
    directly provide a matrix.

    We define an alternate abstract method for implementing classes to define:
    ``_detect_objects_matrix``.  This method is given a numpy ndarray instance
    for the implementing class to utilize.  The return requirements are the same
    as the ``_detect_objects`` method.
    """

    @classmethod
    def get_default_config(cls) -> dict:
        """
        Generate and return a default configuration dictionary for this class.
        This will be primarily used for generating what the configuration
        dictionary would look like for this class without instantiating it.

        By default, we observe what this class's constructor takes as arguments,
        turning those argument names into configuration dictionary keys. If any
        of those arguments have defaults, we will add those values into the
        configuration dictionary appropriately. The dictionary returned should
        only contain JSON compliant value types.

        It is not be guaranteed that the configuration dictionary returned
        from this method is valid for construction of an instance of this class.

        :return: Default configuration dictionary for the class.
        :rtype: dict
        """
        default = super(ImageMatrixObjectDetector, cls).get_default_config()
        default['image_reader'] = make_default_config(ImageReader.get_impls())
        return default

    @classmethod
    def from_config(  # type: ignore
            cls: Type[ImMatObDet],
            config_dict: dict,
            merge_default: bool = True
    ) -> ImMatObDet:
        """
        Instantiate a new instance of this class given the configuration
        JSON-compliant dictionary encapsulating initialization arguments.

        This method should not be called via super unless an instance of the
        class is desired.

        :param config_dict: JSON compliant dictionary encapsulating
            a configuration.
        :type config_dict: dict

        :param merge_default: Merge the given configuration on top of the
            default provided by ``get_default_config``.
        :type merge_default: bool

        :return: Constructed instance from the provided config.
        :rtype: ImageMatrixObjectDetector
        """
        # Shallow copy
        config_dict = dict(config_dict)

        config_dict['image_reader'] = from_config_dict(
            config_dict.get('image_reader', {}), ImageReader.get_impls()
        )

        return super(ImageMatrixObjectDetector, cls).from_config(
            config_dict, merge_default=merge_default
        )

    def __init__(self, image_reader: ImageReader) -> None:
        """
        An image matrix object detector must have a method of converting a
        DataElement into an image pixel matrix so this interface broadly
        requires an :class:`smqtk.algorithms.ImageReader` instance.

        :param smqtk.algorithms.ImageReader image_reader:
            ImageReader algorithm instance for reading image matrices from
            DataElements.
        """
        super(ImageMatrixObjectDetector, self).__init__()
        self._image_reader = image_reader

    @abc.abstractmethod
    def get_config(self) -> dict:
        """
        Return a JSON-compliant dictionary that could be passed to this class's
        ``from_config`` method to produce an instance with identical
        configuration.

        In the most cases, this involves naming the keys of the dictionary
        based on the initialization argument names as if it were to be passed
        to the constructor via dictionary expansion.  In some cases, where it
        doesn't make sense to store some object constructor parameters are
        expected to be supplied at as configuration values (i.e. must be
        supplied at runtime), this method's returned dictionary may leave those
        parameters out. In such cases, the object's ``from_config``
        class-method would also take additional positional arguments to fill in
        for the parameters that this returned configuration lacks.

        :return: JSON type compliant configuration dictionary.
        :rtype: dict

        """
        return {
            'image_reader': to_config_dict(self._image_reader),
        }

    def valid_content_types(self) -> Set[str]:
        """
        :return: A set valid MIME types that are "valid" within the implementing
            class' context.
        :rtype: set[str]
        """
        return self._image_reader.valid_content_types()

    def is_valid_element(self, data_element: DataElement) -> bool:
        """
        Check if the given DataElement instance reports a content type that
        matches one of the MIME types reported by ``valid_content_types``.

        This override uses our stored :class:`ImageReader` algorithm instance to
        define what :class:`DataElement` instances are valid.

        :param smqtk.representation.DataElement data_element:
             Data element instance to check.

        :return: True if the given element has a valid content type as reported
            by ``valid_content_types``, and False if not.
        :rtype: bool
        """
        return self._image_reader.is_valid_element(data_element)

    def _detect_objects(
            self,
            data: DataElement
    ) -> Optional[Iterator[Tuple[AxisAlignedBoundingBox, Dict[Hashable, float]]]]:
        """
        Internal method that defines the generation of paired bounding boxes
        and classification maps for detected objects in the given data.

        This ``ImageMatrixObjectDetector`` implementation ensures that the data
        element is converted to a :class:`numpy.ndarray` before passing the result
        matrix along to the :func:`_detect_objects_matrix` method for the
        implementing class to define.

        :param smqtk.representation.DataElement data:
            Source data (DataElement) from which to detect objects within.

        :return: Iterable over paired ``AxisAlignedBoundingBox`` and
            classification map for detected objects. The returned
            "classification map" should follow the format described by
            ``smqtk.representation.ClassificationElement``: dictionary where
            keys are classification labels and values are classification
            probabilities.
        :rtype:
            collections.abc.Iterator[(smqtk.representation.AxisAlignedBoundingBox,
                                      dict[collections.abc.Hashable, float])]

        """
        mat = self._image_reader.load_as_matrix(data)
        if mat is None:
            return None

        return self._detect_objects_matrix(mat)

    @abc.abstractmethod
    def _detect_objects_matrix(self, mat: numpy.ndarray) \
            -> Iterator[Tuple[AxisAlignedBoundingBox, Dict[Hashable, float]]]:
        """
        Internal method to be implemented that defines the generation of paired
        bounding boxes and classification maps for detected objects in the given
        image matrix data.

        :param numpy.ndarray mat:
            Image pixel matrix to detect objects within.

        :return: Iterable over paired ``AxisAlignedBoundingBox`` and
            classification map for detected objects. The returned
            "classification map" should follow the format described by
            ``smqtk.representation.ClassificationElement``: dictionary where
            keys are classification labels and values are classification
            probabilities.
        :rtype:
            collections.abc.Iterator[(smqtk.representation.AxisAlignedBoundingBox,
                                      dict[collections.abc.Hashable, float])]
        """
