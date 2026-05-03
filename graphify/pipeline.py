from __future__ import annotations

import json
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.detect import detect, save_manifest
from graphify.export import (
    to_canvas,
    to_graphml,
    to_html,
    to_json,
    to_obsidian,
    to_svg,
)
from graphify.report import generate


@dataclass
class ScanConfig:
    project_path: str
    directed: bool = False
    no_viz: bool = False
    include_obsidian: bool = False
    obsidian_dir: Optional[str] = None
    include_svg: bool = False
    include_graphml: bool = False


@dataclass
class ScanProgress:
    step: int
    total_steps: int
    message: str
    nodes: int = 0
    edges: int = 0
    files: int = 0


@dataclass
class ScanResult:
    success: bool
    output_dir: Optional[Path] = None
    graph_path: Optional[Path] = None
    report_path: Optional[Path] = None
    html_path: Optional[Path] = None
    obsidian_dir: Optional[Path] = None
    svg_path: Optional[Path] = None
    graphml_path: Optional[Path] = None
    nodes: int = 0
    edges: int = 0
    communities: int = 0
    error_message: Optional[str] = None
    cancelled: bool = False


@dataclass
class PipelineState:
    output_dir: Path
    detect_result: Dict[str, Any] = field(default_factory=dict)
    ast_result: Dict[str, Any] = field(default_factory=lambda: {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0})
    semantic_result: Dict[str, Any] = field(default_factory=lambda: {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0})
    merged_result: Dict[str, Any] = field(default_factory=lambda: {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0})
    analysis_result: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[int, str] = field(default_factory=dict)
    tokens: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})


class CancelHandler:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def check_cancel(self):
        if self._event.is_set():
            raise InterruptedError("Scan cancelled by user")

    def check_cancel_and_sleep(self, seconds: float = 0.01):
        self.check_cancel()
        if seconds > 0:
            time.sleep(seconds)


class GraphifyPipeline:
    TOTAL_STEPS = 10

    def __init__(
        self,
        config: ScanConfig,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None,
        cancel_handler: Optional[CancelHandler] = None,
    ):
        self.config = config
        self.progress_callback = progress_callback
        self.cancel_handler = cancel_handler or CancelHandler()
        self._check_cancel = self.cancel_handler.check_cancel_and_sleep

    def _update_progress(self, step: int, message: str, nodes: int = 0, edges: int = 0, files: int = 0):
        if self.progress_callback:
            self.progress_callback(ScanProgress(
                step=step,
                total_steps=self.TOTAL_STEPS,
                message=message,
                nodes=nodes,
                edges=edges,
                files=files,
            ))

    def run(self) -> ScanResult:
        try:
            project_path = Path(self.config.project_path).resolve()
            
            output_dir = project_path / "graphify-out"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            state = PipelineState(output_dir=output_dir)
            
            self._check_cancel(0.01)
            
            self._update_progress(1, "检测文件...", files=0)
            self._step_detect(state, project_path)
            
            self._check_cancel(0.01)
            
            has_video = len(state.detect_result.get("files", {}).get("video", [])) > 0
            if has_video:
                self._update_progress(2, "音视频转录...")
                self._step_transcribe(state, project_path)
            
            self._check_cancel(0.01)
            
            self._update_progress(3, "提取代码结构 (AST)...")
            self._step_ast(state, project_path)
            
            self._check_cancel(0.01)
            
            non_code_files = self._count_non_code_files(state)
            if non_code_files > 0:
                self._update_progress(4, "检查语义提取...")
                backend = self._detect_backend()
                
                if backend:
                    self._update_progress(5, f"语义提取 (LLM: {backend})...")
                    self._step_semantic(state, project_path, backend)
                else:
                    self._update_progress(5, "未设置 LLM API Key - 跳过语义提取 (仅 AST)")
            else:
                self._update_progress(4, "无文档/图片文件 - 跳过语义提取检查")
                self._update_progress(5, "仅代码文件 - 跳过语义提取")
            
            self._check_cancel(0.01)
            
            self._update_progress(6, "合并提取结果...")
            self._step_merge(state)
            
            if not state.merged_result["nodes"]:
                return ScanResult(
                    success=False,
                    error_message="No nodes extracted. Check files or try with API key for semantic extraction."
                )
            
            self._check_cancel(0.01)
            
            self._update_progress(7, "构建知识图谱...")
            G, communities, cohesion = self._step_build_graph(state)
            
            self._check_cancel(0.01)
            
            self._update_progress(8, "社区检测...")
            state.labels = {cid: f"Community {cid}" for cid in communities}
            
            self._check_cancel(0.01)
            
            self._update_progress(9, "生成报告...")
            self._step_report(state, project_path, G, communities, cohesion)
            
            self._check_cancel(0.01)
            
            self._update_progress(10, "导出图谱...", nodes=len(state.merged_result["nodes"]), edges=len(state.merged_result["edges"]))
            graph_path = self._step_export(state, G, communities, cohesion)
            
            total_nodes = len(state.merged_result["nodes"])
            total_edges = len(state.merged_result["edges"])
            
            return ScanResult(
                success=True,
                output_dir=state.output_dir,
                graph_path=graph_path,
                report_path=state.output_dir / "GRAPH_REPORT.md",
                html_path=state.output_dir / "graph.html" if not self.config.no_viz else None,
                obsidian_dir=Path(self.config.obsidian_dir) if self.config.include_obsidian and self.config.obsidian_dir else (state.output_dir / "obsidian" if self.config.include_obsidian else None),
                svg_path=state.output_dir / "graph.svg" if self.config.include_svg else None,
                graphml_path=state.output_dir / "graph.graphml" if self.config.include_graphml else None,
                nodes=total_nodes,
                edges=total_edges,
                communities=len(communities),
                cancelled=False,
            )
            
        except InterruptedError:
            return ScanResult(
                success=False,
                cancelled=True,
                error_message="Scan cancelled by user"
            )
        except Exception as e:
            return ScanResult(
                success=False,
                error_message=str(e)
            )

    def _step_detect(self, state: PipelineState, project_path: Path):
        state.detect_result = detect(project_path)
        
        detect_file = state.output_dir / ".graphify_detect.json"
        detect_file.write_text(json.dumps(state.detect_result, indent=2, ensure_ascii=False))
        
        total_files = state.detect_result.get("total_files", 0)
        self._update_progress(1, f"检测文件... 发现 {total_files} 个文件", files=total_files)

    def _step_transcribe(self, state: PipelineState, project_path: Path):
        from graphify.transcribe import transcribe_all
        
        video_files = state.detect_result.get("files", {}).get("video", [])
        if not video_files:
            return
        
        prompt = "Use proper punctuation and paragraph breaks."
        
        try:
            transcript_paths = transcribe_all(
                video_files,
                initial_prompt=prompt,
                output_dir=state.output_dir / "transcripts",
            )
            
            transcripts_file = state.output_dir / ".graphify_transcripts.json"
            transcripts_file.write_text(json.dumps(transcript_paths, indent=2, ensure_ascii=False))
            
            if transcript_paths:
                docs = state.detect_result.get("files", {}).get("document", [])
                for t in transcript_paths:
                    if t not in docs:
                        docs.append(t)
                state.detect_result["files"]["document"] = docs
            
            self._update_progress(2, f"音视频转录... 完成 {len(transcript_paths)} 个")
        except Exception as e:
            self._update_progress(2, f"音视频转录... 跳过: {e}")

    def _step_ast(self, state: PipelineState, project_path: Path):
        from graphify.extract import collect_files, extract
        
        code_files = []
        for f in state.detect_result.get("files", {}).get("code", []):
            p = Path(f)
            if p.is_dir():
                code_files.extend(collect_files(p))
            else:
                code_files.append(p)
        
        if code_files:
            state.ast_result = extract(code_files, cache_root=project_path)
            
            ast_file = state.output_dir / ".graphify_ast.json"
            ast_file.write_text(json.dumps(state.ast_result, indent=2, ensure_ascii=False))
            
            self._update_progress(3, f"提取代码结构... {len(state.ast_result['nodes'])} 节点, {len(state.ast_result['edges'])} 边")
        else:
            self._update_progress(3, "无代码文件 - 跳过 AST 提取")

    def _count_non_code_files(self, state: PipelineState) -> int:
        files = state.detect_result.get("files", {})
        return (
            len(files.get("document", [])) +
            len(files.get("paper", [])) +
            len(files.get("image", []))
        )

    def _detect_backend(self) -> Optional[str]:
        if os.environ.get("MOONSHOT_API_KEY"):
            return "kimi"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"
        return None

    def _step_semantic(self, state: PipelineState, project_path: Path, backend: str):
        from graphify.llm import extract_corpus_parallel
        
        files_dict = state.detect_result.get("files", {})
        all_files: List[Path] = []
        
        for category in ["document", "paper", "image"]:
            for f in files_dict.get(category, []):
                p = Path(f)
                if p.is_file() and p.exists():
                    all_files.append(p)
        
        if not all_files:
            return
        
        self._update_progress(5, f"语义提取... 处理 {len(all_files)} 个文件")
        
        try:
            result = extract_corpus_parallel(
                all_files,
                backend=backend,
                root=project_path,
                max_concurrency=4,
            )
            
            state.semantic_result = result if result else {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
            
            semantic_file = state.output_dir / ".graphify_semantic.json"
            semantic_file.write_text(json.dumps(state.semantic_result, indent=2, ensure_ascii=False))
            
            self._update_progress(5, f"语义提取... {len(state.semantic_result.get('nodes', []))} 节点, {len(state.semantic_result.get('edges', []))} 边")
        except Exception as e:
            self._update_progress(5, f"语义提取失败: {e} - 继续使用 AST 结果")

    def _step_merge(self, state: PipelineState):
        seen = {n["id"] for n in state.ast_result["nodes"]}
        merged_nodes = list(state.ast_result["nodes"])
        
        for n in state.semantic_result.get("nodes", []):
            if n["id"] not in seen:
                merged_nodes.append(n)
                seen.add(n["id"])
        
        merged_edges = state.ast_result["edges"] + state.semantic_result.get("edges", [])
        merged_hyperedges = state.semantic_result.get("hyperedges", [])
        
        input_tokens = state.semantic_result.get("input_tokens", 0)
        output_tokens = state.semantic_result.get("output_tokens", 0)
        
        state.merged_result = {
            "nodes": merged_nodes,
            "edges": merged_edges,
            "hyperedges": merged_hyperedges,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        
        state.tokens = {"input": input_tokens, "output": output_tokens}
        
        extract_file = state.output_dir / ".graphify_extract.json"
        extract_file.write_text(json.dumps(state.merged_result, indent=2, ensure_ascii=False))
        
        self._update_progress(6, f"合并结果... {len(merged_nodes)} 节点 ({len(state.ast_result['nodes'])} AST + {len(state.semantic_result.get('nodes', []))} 语义), {len(merged_edges)} 边")

    def _step_build_graph(self, state: PipelineState) -> Tuple[Any, Dict[int, List[str]], Dict[int, float]]:
        G = build_from_json(state.merged_result, directed=self.config.directed)
        communities = cluster(G)
        cohesion = score_all(G, communities)
        
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels = state.labels
        questions = suggest_questions(G, communities, labels)
        
        state.analysis_result = {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "questions": questions,
        }
        
        analysis_file = state.output_dir / ".graphify_analysis.json"
        analysis_file.write_text(json.dumps(state.analysis_result, indent=2, ensure_ascii=False))
        
        self._update_progress(7, f"构建图谱... {G.number_of_nodes()} 节点, {G.number_of_edges()} 边, {len(communities)} 社区")
        
        return G, communities, cohesion

    def _step_report(self, state: PipelineState, project_path: Path, G: Any, communities: Dict[int, List[str]], cohesion: Dict[int, float]):
        report = generate(
            G,
            communities,
            cohesion,
            state.labels,
            state.analysis_result.get("gods", []),
            state.analysis_result.get("surprises", []),
            state.detect_result,
            state.tokens,
            str(project_path),
            suggested_questions=state.analysis_result.get("questions", []),
        )
        
        report_path = state.output_dir / "GRAPH_REPORT.md"
        report_path.write_text(report, encoding="utf-8")
        
        self._update_progress(9, "生成报告... 完成")

    def _step_export(self, state: PipelineState, G: Any, communities: Dict[int, List[str]], cohesion: Dict[int, float]) -> Path:
        graph_path = state.output_dir / "graph.json"
        to_json(G, communities, str(graph_path))
        
        obsidian_dir = None
        if self.config.include_obsidian:
            if self.config.obsidian_dir:
                obsidian_dir = Path(self.config.obsidian_dir)
            else:
                obsidian_dir = state.output_dir / "obsidian"
            obsidian_dir.mkdir(parents=True, exist_ok=True)
            
            obsidian_count = to_obsidian(
                G,
                communities,
                str(obsidian_dir),
                community_labels=state.labels or None,
                cohesion=cohesion,
            )
            to_canvas(G, communities, str(obsidian_dir / "graph.canvas"), community_labels=state.labels or None)
            
            self._update_progress(10, f"导出 Obsidian... {obsidian_count} 个笔记", nodes=G.number_of_nodes())
        
        if not self.config.no_viz:
            node_limit = 5000
            if G.number_of_nodes() > node_limit:
                from collections import Counter
                import networkx as nx_meta
                
                node_to_community = {nid: cid for cid, members in communities.items() for nid in members}
                meta = nx_meta.Graph()
                
                for cid, members in communities.items():
                    meta.add_node(str(cid), label=state.labels.get(cid, f"Community {cid}"))
                
                edge_counts = Counter()
                for u, v in G.edges():
                    cu, cv = node_to_community.get(u), node_to_community.get(v)
                    if cu is not None and cv is not None and cu != cv:
                        edge_counts[(min(cu, cv), max(cu, cv))] += 1
                
                for (cu, cv), w in edge_counts.items():
                    meta.add_edge(str(cu), str(cv), weight=w, relation=f"{w} cross-community edges", confidence="AGGREGATED")
                
                if meta.number_of_nodes() > 1:
                    meta_communities = {cid: [str(cid)] for cid in communities}
                    member_counts = {cid: len(members) for cid, members in communities.items()}
                    to_html(meta, meta_communities, str(state.output_dir / "graph.html"), community_labels=state.labels or None, member_counts=member_counts)
                else:
                    to_html(G, communities, str(state.output_dir / "graph.html"), community_labels=state.labels or None)
            else:
                to_html(G, communities, str(state.output_dir / "graph.html"), community_labels=state.labels or None)
        
        if self.config.include_svg:
            to_svg(G, communities, str(state.output_dir / "graph.svg"), community_labels=state.labels or None)
        
        if self.config.include_graphml:
            to_graphml(G, communities, str(state.output_dir / "graph.graphml"))
        
        self._save_manifest(state)
        self._update_cost_tracker(state)
        self._cleanup_temp_files(state)
        
        return graph_path

    def _save_manifest(self, state: PipelineState):
        if "files" in state.detect_result:
            save_manifest(state.detect_result["files"])

    def _update_cost_tracker(self, state: PipelineState):
        input_tok = state.merged_result.get("input_tokens", 0)
        output_tok = state.merged_result.get("output_tokens", 0)
        
        cost_path = state.output_dir / "cost.json"
        if cost_path.exists():
            cost = json.loads(cost_path.read_text(encoding="utf-8"))
        else:
            cost = {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0}
        
        cost["runs"].append({
            "date": datetime.now(timezone.utc).isoformat(),
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "files": state.detect_result.get("total_files", 0),
        })
        cost["total_input_tokens"] += input_tok
        cost["total_output_tokens"] += output_tok
        
        cost_path.write_text(json.dumps(cost, indent=2, ensure_ascii=False))

    def _cleanup_temp_files(self, state: PipelineState):
        temp_files = [
            ".graphify_detect.json",
            ".graphify_extract.json",
            ".graphify_ast.json",
            ".graphify_semantic.json",
            ".graphify_analysis.json",
            ".graphify_transcripts.json",
        ]
        
        for f in temp_files:
            p = state.output_dir / f
            if p.exists():
                p.unlink()
        
        for f in state.output_dir.glob(".graphify_chunk_*.json"):
            f.unlink()


def run_pipeline(
    project_path: str,
    directed: bool = False,
    no_viz: bool = False,
    include_obsidian: bool = False,
    obsidian_dir: Optional[str] = None,
    include_svg: bool = False,
    include_graphml: bool = False,
    progress_callback: Optional[Callable[[ScanProgress], None]] = None,
    cancel_handler: Optional[CancelHandler] = None,
) -> ScanResult:
    config = ScanConfig(
        project_path=project_path,
        directed=directed,
        no_viz=no_viz,
        include_obsidian=include_obsidian,
        obsidian_dir=obsidian_dir,
        include_svg=include_svg,
        include_graphml=include_graphml,
    )
    
    pipeline = GraphifyPipeline(
        config=config,
        progress_callback=progress_callback,
        cancel_handler=cancel_handler,
    )
    
    return pipeline.run()
