# Graph Report - ./raw  (2026-04-20)

## Corpus Check
- Large corpus: 17 files · ~1,040,489 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 147 nodes · 193 edges · 22 communities detected
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.81)
- Token cost: 1,438,000 input · 15,000 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Evaluation Pipeline|Evaluation Pipeline]]
- [[_COMMUNITY_3D Box Geometry|3D Box Geometry]]
- [[_COMMUNITY_IoU Computation|IoU Computation]]
- [[_COMMUNITY_Projection & Visibility|Projection & Visibility]]
- [[_COMMUNITY_Performance Metrics|Performance Metrics]]
- [[_COMMUNITY_Dataset Parsing|Dataset Parsing]]
- [[_COMMUNITY_Average Precision|Average Precision]]
- [[_COMMUNITY_Box Sampling|Box Sampling]]
- [[_COMMUNITY_Project Overview|Project Overview]]
- [[_COMMUNITY_Image Visualization|Image Visualization]]
- [[_COMMUNITY_Feature Schema|Feature Schema]]
- [[_COMMUNITY_Notebook Init|Notebook Init]]
- [[_COMMUNITY_Objectron Core Init|Objectron Core Init]]
- [[_COMMUNITY_Dataset Init|Dataset Init]]
- [[_COMMUNITY_Box Rationale (Transform)|Box Rationale (Transform)]]
- [[_COMMUNITY_Box Rationale (Ground Plane)|Box Rationale (Ground Plane)]]
- [[_COMMUNITY_Box Rationale (Vertices)|Box Rationale (Vertices)]]
- [[_COMMUNITY_Box Rationale (Volume)|Box Rationale (Volume)]]
- [[_COMMUNITY_Schema Init|Schema Init]]
- [[_COMMUNITY_Object Schema (Protobuf)|Object Schema (Protobuf)]]
- [[_COMMUNITY_Annotation Data Schema|Annotation Data Schema]]
- [[_COMMUNITY_AR Capture Metadata Schema|AR Capture Metadata Schema]]

## God Nodes (most connected - your core abstractions)
1. `Evaluator` - 23 edges
2. `Box` - 15 edges
3. `IoU` - 14 edges
4. `ObjectronParser` - 13 edges
5. `AveragePrecision` - 9 edges
6. `HitMiss` - 7 edges
7. `main()` - 6 edges
8. `fit()` - 6 edges
9. `Accuracy` - 6 edges
10. `scaled_axis_aligned_vertices()` - 4 edges

## Surprising Connections (you probably didn't know these)
- `ObjectronParser` --semantically_similar_to--> `Object`  [INFERRED] [semantically similar]
  raw/objectron/dataset/parser.py → raw/objectron/schema/object_pb2.py
- `Objectron Dataset Samples GIF` --conceptually_related_to--> `Objectron Dataset`  [INFERRED]
  raw/docs/images/objectron_samples.gif → raw/README.md
- `draw_annotation_on_image()` --references--> `Box`  [EXTRACTED]
  raw/objectron/dataset/graphics.py → raw/objectron/dataset/box.py
- `Evaluator` --calls--> `ObjectronParser`  [EXTRACTED]
  raw/objectron/dataset/eval.py → raw/objectron/dataset/parser.py
- `Evaluator` --calls--> `IoU`  [EXTRACTED]
  raw/objectron/dataset/eval.py → raw/objectron/dataset/iou.py

## Hyperedges (group relationships)
- **Evaluation Flow** — eval_evaluator, metrics_averageprecision, iou_iou, parser_objectronparser [INFERRED 0.95]
- **Dataset Core Concepts** — readme_objectron_dataset, readme_3d_bounding_boxes, readme_ar_metadata [EXTRACTED 1.00]

## Communities

### Community 0 - "Evaluation Pipeline"
Cohesion: 0.1
Nodes (16): Evaluator, main(), Example Evaluation script for Objectron dataset.  It reads a tfrecord, runs eval, Evaluates a box in 3D.      It computes metrics of view angle and 3D IoU.      A, Computes scale of the given box sitting on the plane., Computes a ray from camera to box centroid in box frame.      For vertex in came, Computes Average Distance (ADD) metric., Computes viewpoint of a 3D bounding box.      We use the definition of polar ang (+8 more)

### Community 1 - "3D Box Geometry"
Cohesion: 0.13
Nodes (12): Box, fit(), from_transformation(), General 3D Bounding Box class., Get ground plane under the box., General 3D Oriented Bounding Box., Applies transformation on the box.      Group multiplication is the same as rota, rotation() (+4 more)

### Community 2 - "IoU Computation"
Cohesion: 0.13
Nodes (10): IoU, The Intersection Over Union (IoU) for 3D oriented bounding boxes., Clips the polygon with the plane using the Sutherland-Hodgman algorithm.      Se, General Intersection Over Union cost for Oriented 3D bounding boxes., Computes the intersection of a line with an axis-aligned plane.      Args:, Check whether a given point is on a 2D plane., Classify position of a point w.r.t the given plane.      See Real-Time Collision, Computes the exact IoU using Sutherland-Hodgman algorithm. (+2 more)

### Community 3 - "Projection & Visibility"
Cohesion: 0.14
Nodes (7): Evaluates a pair of 2D projections of 3D boxes.      It computes the mean normal, Matches a detected box with annotated instances.      For a predicted box, finds, Determines if a 2D point is visible., Implement your own function/model to predict the box's 2D and 3D        keypoint, Evaluates a batch of serialized tf.Example protos., Parses camera from a tensorflow example., Parses plane from a tensorflow example.

### Community 4 - "Performance Metrics"
Cohesion: 0.15
Nodes (8): Accuracy, HitMiss, Util classes for computing evaluation metrics., Class for accuracy metric., Computes accuracy for a given threshold., Records the hit or miss for the object based on the metric threshold., Class for recording hits and misses of detection results., object

### Community 5 - "Dataset Parsing"
Cohesion: 0.19
Nodes (7): FEATURE_NAMES, Object, ObjectronParser, Parser for Objectron tf.examples., Normalizes pixels of an image from [0, 1] to [-1, 1]., Gets image and its label from a serialized tf.Example.      Args:       serializ, Parses image and label from a tf.Example proto.      Args:       example: A tf.E

### Community 6 - "Average Precision"
Cohesion: 0.27
Nodes (4): AveragePrecision, Class for computing average precision., Calculates the AP given the recall and precision array.      The reference imple, Computes the precision/recall curve.

### Community 7 - "Box Sampling"
Cohesion: 0.33
Nodes (3): Tests whether a given point is inside the box.        Brings the 3D point into t, Samples a 3D point uniformly inside this box., Computes intersection over union by sampling points.      Generate n samples ins

### Community 8 - "Project Overview"
Cohesion: 0.4
Nodes (5): Objectron Dataset Samples GIF, 3D Bounding Boxes, AR Metadata, MediaPipe, Objectron Dataset

### Community 9 - "Image Visualization"
Cohesion: 0.5
Nodes (3): draw_annotation_on_image(), Methods for drawing a bounding box on an image., Draw annotation on the image.

### Community 10 - "Feature Schema"
Cohesion: 1.0
Nodes (1): Features in Objectron's tf.Example.

### Community 11 - "Notebook Init"
Cohesion: 1.0
Nodes (0): 

### Community 12 - "Objectron Core Init"
Cohesion: 1.0
Nodes (0): 

### Community 13 - "Dataset Init"
Cohesion: 1.0
Nodes (0): 

### Community 14 - "Box Rationale (Transform)"
Cohesion: 1.0
Nodes (1): Constructs an oriented bounding box from transformation and scale.

### Community 15 - "Box Rationale (Ground Plane)"
Cohesion: 1.0
Nodes (1): Returns an axis-aligned set of verticies for a box of the given scale.      Args

### Community 16 - "Box Rationale (Vertices)"
Cohesion: 1.0
Nodes (1): Estimates a box 9-dof parameters from the given vertices.      Directly computes

### Community 17 - "Box Rationale (Volume)"
Cohesion: 1.0
Nodes (1): Compute the volume of the parallelpiped or the box.        For the boxes, this i

### Community 18 - "Schema Init"
Cohesion: 1.0
Nodes (0): 

### Community 19 - "Object Schema (Protobuf)"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Annotation Data Schema"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "AR Capture Metadata Schema"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **61 isolated node(s):** `Methods for drawing a bounding box on an image.`, `Draw annotation on the image.`, `Example Evaluation script for Objectron dataset.  It reads a tfrecord, runs eval`, `Class for evaluating the Objectron's model.`, `Implement your own function/model to predict the box's 2D and 3D        keypoint` (+56 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Feature Schema`** (2 nodes): `Features in Objectron's tf.Example.`, `features.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Notebook Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Objectron Core Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Dataset Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Box Rationale (Transform)`** (1 nodes): `Constructs an oriented bounding box from transformation and scale.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Box Rationale (Ground Plane)`** (1 nodes): `Returns an axis-aligned set of verticies for a box of the given scale.      Args`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Box Rationale (Vertices)`** (1 nodes): `Estimates a box 9-dof parameters from the given vertices.      Directly computes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Box Rationale (Volume)`** (1 nodes): `Compute the volume of the parallelpiped or the box.        For the boxes, this i`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Schema Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Object Schema (Protobuf)`** (1 nodes): `object_pb2.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Annotation Data Schema`** (1 nodes): `annotation_data_pb2.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `AR Capture Metadata Schema`** (1 nodes): `a_r_capture_metadata_pb2.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Evaluator` connect `Evaluation Pipeline` to `IoU Computation`, `Projection & Visibility`, `Performance Metrics`, `Dataset Parsing`, `Average Precision`?**
  _High betweenness centrality (0.319) - this node is a cross-community bridge._
- **Why does `Box` connect `3D Box Geometry` to `Evaluation Pipeline`, `IoU Computation`, `Performance Metrics`, `Box Sampling`, `Image Visualization`?**
  _High betweenness centrality (0.275) - this node is a cross-community bridge._
- **Why does `IoU` connect `IoU Computation` to `Evaluation Pipeline`, `3D Box Geometry`, `Performance Metrics`, `Box Sampling`?**
  _High betweenness centrality (0.210) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Box` (e.g. with `.evaluate_rotation()` and `.evaluate_iou()`) actually correct?**
  _`Box` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `ObjectronParser` (e.g. with `.__init__()` and `Object`) actually correct?**
  _`ObjectronParser` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Methods for drawing a bounding box on an image.`, `Draw annotation on the image.`, `Example Evaluation script for Objectron dataset.  It reads a tfrecord, runs eval` to the rest of the system?**
  _61 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Evaluation Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._