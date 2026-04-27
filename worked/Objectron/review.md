# Objectron Code Repository Graphification Review

**Corpus:** (https://github.com/google-research-datasets/Objectron) : a 3D bounding box evaluation pipeline for AR/ML object detection with TensorFlow integration, IoU computation, and metrics.

**Files:** 17 files (~1M words)  
**Graph:** 147 nodes · 193 edges · 22 communities  
**Token cost:** 1,438,000 input · 15,000 output (using gemini-3-flash)

---

## Community Detection

| Community | Label | Cohesion | Nodes | Finding |
|-----------|-------|----------|-------|---------|
| 0 | Evaluation Pipeline | 0.10 | 16 | **CORRECT** - Contains `Evaluator`, `main()`, and all evaluation rationale nodes. Low cohesion (0.10) reflects the fact that evaluation methods fan out to different subsystems (metrics, IoU, parsing) rather than calling each other sequentially |
| 1 | 3D Box Geometry | 0.13 | 12 | **CORRECT** - `Box` class with transformation methods (`fit()`, `from_transformation()`, `apply_transformation()`). Slightly higher cohesion than evaluation because geometric operations chain together |
| 2 | IoU Computation | 0.13 | 10 | **CORRECT** - `IoU` class and Sutherland-Hodgman polygon clipping methods. Self-contained algorithm module |
| 3 | Projection & Visibility | 0.14 | 7 | **CORRECT** - 2D projection evaluation, camera/plane parsing, visibility checks. Bridges evaluation pipeline to parser |

---

## What the graph got right

**Hyperedge between God nodes map correctly models evaluation architecture** : Grouping `Evaluator`, `AveragePrecision`, `IoU`, and `ObjectronParser` as a single conceptual unit correctly describes the pieces needed for the evaluation pipeline.

**Some insighful semantic connections** :  Graphify inferred a semantic similarity edge from `parser.py` to the protobuf-generated `object_pb2.py`. This is a non-explicit relationship as The parser produces `Object` instances but the protobuf file is auto-generated, and a new entrant to would be able to spot this data flow connection at-a-glance.

**Identifies cross-module dependencies** : Visualization code in `graphics.py` depends on `Box` geometry i.e
`draw_annotation_on_image()` receives box geometry to work.

---

## Query Tests

## Q1 : What does evaluate() do and how does it connect to Box?
   - BFS from eval_evaluator_evaluate() reached 129 nodes in the connected component.
   - The evaluate_iou() method (within the Evaluator class in eval.py) directly references the Box class (defined in box.py). This connection occurs when evaluate_iou() instantiates Box objects from raw data for IoU computation.
   - Saved: graphify-out/memory/query_20260427_193034_what_does_evaluate_do_and_how_does_it_connect_to_b.md


## Q2 : What does .iou() analyze?
   - BFS from iou_iou_iou reached 129 nodes in the connected component.
   - The .iou() method (within the IoU class in iou.py) analyzes the Intersection Over Union (IoU) between two 3D oriented bounding box objects. It is designed to quantify the overlap between a predicted 3D bounding box and a ground-truth 3D bounding box, typically utilizing the Sutherland-Hodgman algorithm for precise intersection calculation.
   - Saved: graphify-out/memory/query_20260427_193207_what_does__iou___analyze.md

## Q3 : What do the hyperedges in the graph highlight specifically?
   - BFS from eval_evaluator (a central node in the "Evaluation Flow" hyperedge) reached 129 nodes in the connected component.
   - The hyperedges highlight coherent group relationships between multiple nodes that are not fully captured by pairwise edges.
       - Evaluation Flow: This hyperedge (comprising Evaluator, AveragePrecision, IoU, and ObjectronParser) underscores the integrated process of evaluating model performance, from parsing data to computing key metrics. It emphasizes the collective role these components play in assessing object detection quality.
       - Dataset Core Concepts: This hyperedge (grouping Objectron Dataset, 3D Bounding Boxes, and AR Metadata) outlines
         the foundational elements of the Objectron dataset's structure and content as detailed in the README.md.
   - Saved: graphify-out/memory/query_20260427_193325_what_do_the_hyperedges_in_the_graph_highlight_spec.md
 
## Feedback Loop Test

```
  Memory files created: 3
    query_20260427_193034_what_does_evaluate_do_and_how_does_it_connect_to_b.md   875 bytes
    query_20260427_193207_what_does__iou___analyze.md                          897 bytes
    query_20260427_193325_what_do_the_hyperedges_in_the_graph_highlight_spec.md 1.3K bytes
    
    detect() on current root with graphify-out/memory/ present:
    Memory files found by next scan: 3 / 3  ✓
```
**Result: PASS.** All 3 query results appear in the next `detect()` scan. On the next `--update`, these files will be extracted as nodes in the graph.


## Scores 

| Dimension | Score | Notes |
|-----------|-------|-------|
| Detection accuracy | 10/10 | Code/docs/metadata identified accurately; schema detection robust |
| AST extraction | 9/10 | Python modules/symbols correctly mapped; strong linkage to geometry primitives |
| Community quality | 9/10 | Communities (e.g., Evaluation, Geometry, IoU) map perfectly to functional modules |
| Query traversal | 9/10 | BFS paths accurately identify connections between Evaluator and Box |
| Feedback loop | 10/10 | All 3 query results captured by detect() scan, ready for incremental re-extraction |

Overall: 9.4/10 — Excellent performance across all tested dimensions.The primary strengths lie in the clear mapping of the evaluation pipeline and the high-fidelity feedback loop. The slight gap remains in edge-level semantics, specifically the potential for deeper inferred couplings (e.g., latent dependencies not strictly defined by structural calls)

## Issues found

 
**Semantic inference could be stronger** : A connecting edge between the Objectron Dataset samples and the Evaluator would be an insightful "surprising connection" to spot, as the repository is not so cleanly seperated for this connection to be completely missed. This might highlight challenges in building structual connections across modalities.


**Multiple isolated/weakly connected rationale nodes**: A good amount of "rationale" nodes are either isolated/ weakly connected i.e `"Example Evaluation script for Objectron dataset"` and `"Class for evaluating the Objectron's model"`. These conceptual nodes could not connect them to the code they describe.

---
