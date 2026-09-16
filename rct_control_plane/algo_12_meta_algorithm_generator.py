"""
ALGO-12: Meta-Algorithm Generator Engine

Ported from Delentia-Private-OS's real implementation at
rct_platform/microservices/meta-algorithm-generator/app/core/meta_algorithm_engine.py.
No FastAPI/HTTP route code lived in the source module — it was already a
plain class with its own `if __name__ == "__main__":` smoke test — so
this is effectively a straight copy of the real composition logic for
all 5 modes (sequential/parallel/conditional/iterative/recursive),
which is pure in-memory Python (dataclass registry + graph-building +
validation), plus the algorithm registry and generation-session tracking.

Implements meta-function Gamma: (f1, f2, ..., fn) -> F
- Composition: Gamma(f, g) = f o g where (f o g)(x) = f(g(x))
- Chain: Gamma(f1, ..., fn) = f1 o f2 o ... o fn
- Validation: V(F) -> {valid, invalid} + reasons

PORTING NOTE — optional LLM naming call: the source's
`_generate_composition_name()` makes an OPTIONAL call to a local Ollama
server via `httpx.AsyncClient` to generate a display name, with a
harmless hardcoded fallback (`"{Mode} Composition"`) wrapped in a bare
`except:` if that call fails or times out. `httpx` is NOT listed in
Delentia-OS's pyproject.toml dependencies (base or optional) — per the
porting brief, this is reported as a finding rather than silently added.
To keep the module importable without a new hard dependency, the
`httpx` import here is wrapped in `try/except ImportError` behind an
`_HAS_HTTPX` flag; when httpx isn't installed, `_generate_composition_name()`
skips straight to the same hardcoded fallback the source already used on
any LLM-call failure — this changes nothing about the documented
fallback behavior for the (very common, in a fresh Delentia-OS install)
case where no local Ollama server is even reachable in the first place.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:  # httpx not declared in Delentia-OS/pyproject.toml — see module docstring
    httpx = None  # type: ignore[assignment]
    _HAS_HTTPX = False


class CompositionMode(str, Enum):
    """Algorithm composition modes"""
    SEQUENTIAL = "sequential"      # f1 -> f2 -> f3
    PARALLEL = "parallel"          # [f1, f2, f3] -> merge
    CONDITIONAL = "conditional"    # if(c) then f1 else f2
    ITERATIVE = "iterative"        # repeat f until condition
    RECURSIVE = "recursive"        # f calls f with modified input


class AlgorithmType(str, Enum):
    """Base algorithm types"""
    TRANSFORM = "transform"        # Input -> Output transformation
    FILTER = "filter"             # Input -> Filtered Output
    AGGREGATE = "aggregate"       # [Inputs] -> Single Output
    GENERATE = "generate"         # Seed -> Generated Output
    ANALYZE = "analyze"           # Input -> Analysis
    OPTIMIZE = "optimize"         # Input -> Optimized Output


class ValidationStatus(str, Enum):
    """Validation result status"""
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


@dataclass
class BaseAlgorithm:
    """
    Base algorithm component

    Represents atomic algorithm f with:
    - Signature: Input -> Output
    - Type: Transform, Filter, etc.
    - Constraints: Pre/post conditions
    """
    id: str
    name: str
    algorithm_type: AlgorithmType
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    complexity: str = "O(n)"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComposedAlgorithm:
    """
    Composed algorithm F = Gamma(f1, f2, ..., fn)

    Represents meta-algorithm created by composing base algorithms
    """
    id: str
    name: str
    components: List[str]  # IDs of base algorithms
    composition_mode: CompositionMode
    composition_graph: Dict[str, Any]  # DAG or sequence representation
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    validation_result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class CompositionRequest:
    """Request to compose algorithms"""
    component_ids: List[str]
    mode: CompositionMode
    goal: str
    constraints: List[str] = field(default_factory=list)
    optimization_target: Optional[str] = None


@dataclass
class ValidationResult:
    """Algorithm validation result"""
    status: ValidationStatus
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    complexity_analysis: Optional[str] = None


@dataclass
class GenerationSession:
    """Meta-algorithm generation session"""
    session_id: str
    request: CompositionRequest
    composed_algorithm: Optional[ComposedAlgorithm] = None
    validation_result: Optional[ValidationResult] = None
    status: str = "pending"  # pending, composing, validating, complete, failed
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class MetaAlgorithmEngine:
    """
    Meta-Algorithm Generator Engine

    Implements:
    1. Algorithm Registry - Store base algorithms
    2. Composition - Gamma: (f1, ..., fn) -> F
    3. Validation - V(F) -> {valid, invalid}
    4. Generation - G(goal) -> F
    """

    def __init__(
        self,
        llm_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        max_composition_depth: int = 5
    ):
        self.llm_url = llm_url
        self.model = model
        self.max_composition_depth = max_composition_depth

        # Algorithm registry
        self.base_algorithms: Dict[str, BaseAlgorithm] = {}
        self.composed_algorithms: Dict[str, ComposedAlgorithm] = {}
        self.sessions: Dict[str, GenerationSession] = {}

        # Initialize with default algorithms
        self._initialize_default_algorithms()

    def _initialize_default_algorithms(self):
        """Initialize registry with basic algorithms"""

        # Transform algorithms
        self.register_algorithm(BaseAlgorithm(
            id="map",
            name="Map",
            algorithm_type=AlgorithmType.TRANSFORM,
            description="Apply function to each element",
            input_schema={"type": "array", "items": "any"},
            output_schema={"type": "array", "items": "any"},
            complexity="O(n)"
        ))

        self.register_algorithm(BaseAlgorithm(
            id="reduce",
            name="Reduce",
            algorithm_type=AlgorithmType.AGGREGATE,
            description="Aggregate elements to single value",
            input_schema={"type": "array", "items": "any"},
            output_schema={"type": "any"},
            complexity="O(n)"
        ))

        # Filter algorithms
        self.register_algorithm(BaseAlgorithm(
            id="filter",
            name="Filter",
            algorithm_type=AlgorithmType.FILTER,
            description="Select elements matching predicate",
            input_schema={"type": "array", "items": "any"},
            output_schema={"type": "array", "items": "any"},
            complexity="O(n)"
        ))

        # Analysis algorithms
        self.register_algorithm(BaseAlgorithm(
            id="analyze",
            name="Analyze",
            algorithm_type=AlgorithmType.ANALYZE,
            description="Extract insights from data",
            input_schema={"type": "any"},
            output_schema={"type": "object", "properties": {"insights": "array"}},
            complexity="O(n)"
        ))

        # Optimization algorithms
        self.register_algorithm(BaseAlgorithm(
            id="optimize",
            name="Optimize",
            algorithm_type=AlgorithmType.OPTIMIZE,
            description="Improve solution quality",
            input_schema={"type": "any"},
            output_schema={"type": "any"},
            complexity="O(n log n)"
        ))

        # Generation algorithms
        self.register_algorithm(BaseAlgorithm(
            id="generate",
            name="Generate",
            algorithm_type=AlgorithmType.GENERATE,
            description="Create new instances from template",
            input_schema={"type": "object", "properties": {"template": "string"}},
            output_schema={"type": "array", "items": "any"},
            complexity="O(k)"
        ))

    def register_algorithm(self, algorithm: BaseAlgorithm):
        """Register base algorithm in registry"""
        self.base_algorithms[algorithm.id] = algorithm

    def get_algorithm(self, algorithm_id: str) -> Optional[BaseAlgorithm]:
        """Get algorithm by ID"""
        return self.base_algorithms.get(algorithm_id)

    def list_algorithms(self) -> List[Dict[str, Any]]:
        """List all registered algorithms"""
        return [asdict(algo) for algo in self.base_algorithms.values()]

    async def compose(
        self,
        component_ids: List[str],
        mode: CompositionMode,
        goal: str,
        constraints: List[str] = None
    ) -> str:
        """
        Compose algorithms into meta-algorithm

        Gamma: (f1, f2, ..., fn) -> F

        Args:
            component_ids: IDs of algorithms to compose
            mode: Composition mode (sequential, parallel, etc.)
            goal: What the composed algorithm should achieve
            constraints: Composition constraints

        Returns:
            session_id: Session ID for tracking
        """
        session_id = self._generate_session_id()

        # Create request
        request = CompositionRequest(
            component_ids=component_ids,
            mode=mode,
            goal=goal,
            constraints=constraints or []
        )

        # Create session
        session = GenerationSession(
            session_id=session_id,
            request=request,
            status="composing"
        )
        self.sessions[session_id] = session

        try:
            # Validate components exist
            components = []
            for comp_id in component_ids:
                algo = self.get_algorithm(comp_id)
                if not algo:
                    session.status = "failed"
                    session.error = f"Algorithm '{comp_id}' not found"
                    return session_id
                components.append(algo)

            # Compose based on mode
            if mode == CompositionMode.SEQUENTIAL:
                composed = await self._compose_sequential(components, goal)
            elif mode == CompositionMode.PARALLEL:
                composed = await self._compose_parallel(components, goal)
            elif mode == CompositionMode.CONDITIONAL:
                composed = await self._compose_conditional(components, goal)
            elif mode == CompositionMode.ITERATIVE:
                composed = await self._compose_iterative(components, goal)
            elif mode == CompositionMode.RECURSIVE:
                composed = await self._compose_recursive(components, goal)
            else:
                session.status = "failed"
                session.error = f"Unsupported composition mode: {mode}"
                return session_id

            session.composed_algorithm = composed
            session.status = "validating"

            # Validate composition
            validation = await self._validate_composition(composed, constraints or [])
            session.validation_result = validation

            if validation.is_valid:
                # Store composed algorithm
                self.composed_algorithms[composed.id] = composed
                session.status = "complete"
            else:
                session.status = "failed"
                session.error = f"Validation failed: {', '.join(validation.errors)}"

        except Exception as e:
            session.status = "failed"
            session.error = str(e)

        return session_id

    async def _compose_sequential(
        self,
        components: List[BaseAlgorithm],
        goal: str
    ) -> ComposedAlgorithm:
        """
        Sequential composition: f1 o f2 o ... o fn

        Output of fi becomes input of fi+1
        """
        comp_id = f"composed-seq-{uuid.uuid4().hex[:8]}"

        # Build composition graph (linear chain)
        graph = {
            "type": "sequential",
            "nodes": [{"id": algo.id, "name": algo.name} for algo in components],
            "edges": [
                {"from": components[i].id, "to": components[i+1].id}
                for i in range(len(components) - 1)
            ]
        }

        # Input schema = first component's input
        input_schema = components[0].input_schema

        # Output schema = last component's output
        output_schema = components[-1].output_schema

        # Generate name and description
        name = await self._generate_composition_name(components, "sequential", goal)

        return ComposedAlgorithm(
            id=comp_id,
            name=name,
            components=[c.id for c in components],
            composition_mode=CompositionMode.SEQUENTIAL,
            composition_graph=graph,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata={
                "goal": goal,
                "component_count": len(components),
                "composition_type": "sequential"
            }
        )

    async def _compose_parallel(
        self,
        components: List[BaseAlgorithm],
        goal: str
    ) -> ComposedAlgorithm:
        """
        Parallel composition: [f1, f2, ..., fn] -> merge

        All components process same input, outputs merged
        """
        comp_id = f"composed-par-{uuid.uuid4().hex[:8]}"

        # Build composition graph (fan-out, fan-in)
        graph = {
            "type": "parallel",
            "nodes": [{"id": algo.id, "name": algo.name} for algo in components],
            "edges": [
                {"from": "input", "to": algo.id} for algo in components
            ] + [
                {"from": algo.id, "to": "merge"} for algo in components
            ]
        }

        # Input schema = union of all component inputs
        input_schema = {"type": "any"}  # Simplified

        # Output schema = merged outputs
        output_schema = {
            "type": "object",
            "properties": {
                comp.id: comp.output_schema for comp in components
            }
        }

        name = await self._generate_composition_name(components, "parallel", goal)

        return ComposedAlgorithm(
            id=comp_id,
            name=name,
            components=[c.id for c in components],
            composition_mode=CompositionMode.PARALLEL,
            composition_graph=graph,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata={
                "goal": goal,
                "component_count": len(components),
                "composition_type": "parallel"
            }
        )

    async def _compose_conditional(
        self,
        components: List[BaseAlgorithm],
        goal: str
    ) -> ComposedAlgorithm:
        """
        Conditional composition: if(condition) then f1 else f2

        Route to different algorithms based on condition
        """
        comp_id = f"composed-cond-{uuid.uuid4().hex[:8]}"

        # Need at least 2 components
        if len(components) < 2:
            components = components + components  # Duplicate if only one

        graph = {
            "type": "conditional",
            "nodes": [{"id": algo.id, "name": algo.name} for algo in components],
            "condition": "dynamic",  # Determined at runtime
            "branches": {
                "true": components[0].id,
                "false": components[1].id if len(components) > 1 else components[0].id
            }
        }

        # Input/output schemas unified
        input_schema = {"type": "any"}
        output_schema = {"type": "any"}

        name = await self._generate_composition_name(components, "conditional", goal)

        return ComposedAlgorithm(
            id=comp_id,
            name=name,
            components=[c.id for c in components],
            composition_mode=CompositionMode.CONDITIONAL,
            composition_graph=graph,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata={
                "goal": goal,
                "component_count": len(components),
                "composition_type": "conditional"
            }
        )

    async def _compose_iterative(
        self,
        components: List[BaseAlgorithm],
        goal: str
    ) -> ComposedAlgorithm:
        """
        Iterative composition: repeat f until condition

        Apply algorithm repeatedly until termination condition
        """
        comp_id = f"composed-iter-{uuid.uuid4().hex[:8]}"

        # Use first component as iteration body
        body = components[0]

        graph = {
            "type": "iterative",
            "body": {"id": body.id, "name": body.name},
            "termination": "convergence or max_iterations",
            "max_iterations": 100
        }

        input_schema = body.input_schema
        output_schema = body.output_schema

        name = await self._generate_composition_name(components, "iterative", goal)

        return ComposedAlgorithm(
            id=comp_id,
            name=name,
            components=[c.id for c in components],
            composition_mode=CompositionMode.ITERATIVE,
            composition_graph=graph,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata={
                "goal": goal,
                "component_count": len(components),
                "composition_type": "iterative"
            }
        )

    async def _compose_recursive(
        self,
        components: List[BaseAlgorithm],
        goal: str
    ) -> ComposedAlgorithm:
        """
        Recursive composition: f calls f with modified input

        Divide-and-conquer or recursive refinement
        """
        comp_id = f"composed-rec-{uuid.uuid4().hex[:8]}"

        body = components[0]

        graph = {
            "type": "recursive",
            "body": {"id": body.id, "name": body.name},
            "base_case": "input size <= threshold",
            "recursive_call": "f(subdivided_input)",
            "combine": "merge results"
        }

        input_schema = body.input_schema
        output_schema = body.output_schema

        name = await self._generate_composition_name(components, "recursive", goal)

        return ComposedAlgorithm(
            id=comp_id,
            name=name,
            components=[c.id for c in components],
            composition_mode=CompositionMode.RECURSIVE,
            composition_graph=graph,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata={
                "goal": goal,
                "component_count": len(components),
                "composition_type": "recursive"
            }
        )

    async def _generate_composition_name(
        self,
        components: List[BaseAlgorithm],
        mode: str,
        goal: str
    ) -> str:
        """Generate descriptive name for composed algorithm using LLM (optional, with fallback)"""

        component_names = [c.name for c in components]

        if _HAS_HTTPX:
            prompt = f"""Generate a concise, descriptive name for a composed algorithm.

Components: {', '.join(component_names)}
Composition Mode: {mode}
Goal: {goal}

Generate a clear name (2-4 words) that describes what this algorithm does.
Respond with just the name, nothing else."""

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.llm_url}/api/generate",
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "stream": False
                        }
                    )

                    if response.status_code == 200:
                        result = response.json()
                        name = result.get("response", "").strip()
                        # Clean up
                        name = name.replace('"', '').replace("'", "")
                        if name:
                            return name
            except Exception:
                pass

        # Fallback (also the path taken when httpx isn't installed at all —
        # same behavior the source already had for any LLM-call failure)
        return f"{mode.capitalize()} Composition"

    async def _validate_composition(
        self,
        composed: ComposedAlgorithm,
        constraints: List[str]
    ) -> ValidationResult:
        """
        Validate composed algorithm

        Checks:
        1. Type compatibility (output of fi matches input of fi+1)
        2. Precondition satisfaction
        3. Constraint compliance
        4. Complexity analysis
        """
        errors = []
        warnings = []
        suggestions = []

        # Get component algorithms
        components = [
            self.get_algorithm(comp_id)
            for comp_id in composed.components
        ]

        # Check all components exist
        if None in components:
            errors.append("One or more component algorithms not found")
            return ValidationResult(
                status=ValidationStatus.INVALID,
                is_valid=False,
                errors=errors
            )

        # Type compatibility for sequential composition
        if composed.composition_mode == CompositionMode.SEQUENTIAL:
            for i in range(len(components) - 1):
                current = components[i]
                next_comp = components[i + 1]

                # Simplified type checking
                if current.output_schema.get("type") != next_comp.input_schema.get("type"):
                    if current.output_schema.get("type") != "any" and next_comp.input_schema.get("type") != "any":
                        warnings.append(
                            f"Type mismatch between {current.name} output and {next_comp.name} input"
                        )

        # Check depth
        if len(components) > self.max_composition_depth:
            warnings.append(
                f"Composition depth ({len(components)}) exceeds recommended maximum ({self.max_composition_depth})"
            )

        # Complexity analysis
        complexities = [comp.complexity for comp in components]
        overall_complexity = self._analyze_complexity(complexities, composed.composition_mode)

        # Check constraints
        for constraint in constraints:
            # Simplified constraint checking
            if "performance" in constraint.lower():
                if "n^2" in overall_complexity or "n^3" in overall_complexity:
                    warnings.append("Performance constraint may not be met - high complexity detected")

        # Generate suggestions
        if warnings:
            suggestions.append("Consider simplifying the composition or optimizing component algorithms")

        is_valid = len(errors) == 0
        status = ValidationStatus.VALID if is_valid else (
            ValidationStatus.WARNING if warnings else ValidationStatus.VALID
        )

        return ValidationResult(
            status=status,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            complexity_analysis=overall_complexity
        )

    def _analyze_complexity(self, complexities: List[str], mode: CompositionMode) -> str:
        """Analyze overall complexity of composition"""

        if mode == CompositionMode.SEQUENTIAL:
            # Sequential: sum of complexities, dominated by highest
            if any("n^3" in c for c in complexities):
                return "O(n^3)"
            elif any("n^2" in c for c in complexities):
                return "O(n^2)"
            elif any("n log n" in c for c in complexities):
                return "O(n log n)"
            else:
                return "O(n)"

        elif mode == CompositionMode.PARALLEL:
            # Parallel: max of complexities (assuming true parallelism)
            if any("n^3" in c for c in complexities):
                return "O(n^3)"
            elif any("n^2" in c for c in complexities):
                return "O(n^2)"
            elif any("n log n" in c for c in complexities):
                return "O(n log n)"
            else:
                return "O(n)"

        elif mode == CompositionMode.ITERATIVE:
            # Iterative: O(k x complexity) where k = iterations
            base = complexities[0] if complexities else "O(n)"
            return f"O(k x {base})"

        elif mode == CompositionMode.RECURSIVE:
            # Recursive: depends on divide strategy
            return "O(n log n)"  # Typical for divide-and-conquer

        else:
            return "O(n)"

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get generation session details"""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        result = {
            "session_id": session.session_id,
            "status": session.status,
            "timestamp": session.timestamp
        }

        if session.composed_algorithm:
            result["composed_algorithm"] = asdict(session.composed_algorithm)

        if session.validation_result:
            result["validation_result"] = asdict(session.validation_result)

        if session.error:
            result["error"] = session.error

        return result

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all generation sessions"""
        return [
            {
                "session_id": s.session_id,
                "status": s.status,
                "goal": s.request.goal,
                "timestamp": s.timestamp
            }
            for s in self.sessions.values()
        ]

    def get_composed_algorithm(self, algorithm_id: str) -> Optional[Dict[str, Any]]:
        """Get composed algorithm by ID"""
        algo = self.composed_algorithms.get(algorithm_id)
        if algo:
            return asdict(algo)
        return None

    def list_composed_algorithms(self) -> List[Dict[str, Any]]:
        """List all composed algorithms"""
        return [asdict(algo) for algo in self.composed_algorithms.values()]

    def delete_session(self, session_id: str) -> bool:
        """Delete generation session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return f"meta-gen-{uuid.uuid4().hex[:12]}"


if __name__ == "__main__":
    import asyncio

    async def _smoke_test():
        print("=" * 70)
        print("ALGO-12 META-ALGORITHM GENERATOR — smoke test")
        print(f"httpx available: {_HAS_HTTPX} (LLM naming call will "
              f"{'attempt and fall back on failure' if _HAS_HTTPX else 'be skipped straight to the hardcoded fallback'})")
        print("=" * 70)

        engine = MetaAlgorithmEngine()

        base_algos = engine.list_algorithms()
        print(f"Base algorithms registered: {len(base_algos)}")
        assert len(base_algos) == 6

        # Sequential composition
        session_id = await engine.compose(
            component_ids=["filter", "map", "reduce"],
            mode=CompositionMode.SEQUENTIAL,
            goal="Process and aggregate filtered data"
        )
        session = engine.get_session(session_id)
        print(f"Sequential compose -> status={session['status']}")
        assert session["status"] == "complete"
        assert session["composed_algorithm"]["composition_mode"] == "sequential"
        assert len(session["composed_algorithm"]["composition_graph"]["edges"]) == 2
        assert session["validation_result"]["is_valid"] is True
        print(f"  name={session['composed_algorithm']['name']!r} "
              f"complexity={session['validation_result']['complexity_analysis']}")

        # Parallel composition
        session_id2 = await engine.compose(
            component_ids=["analyze", "optimize"],
            mode=CompositionMode.PARALLEL,
            goal="Analyze and optimize simultaneously"
        )
        session2 = engine.get_session(session_id2)
        print(f"Parallel compose -> status={session2['status']}")
        assert session2["status"] == "complete"
        assert session2["composed_algorithm"]["composition_mode"] == "parallel"

        # Unknown component -> real failure path, not swallowed
        bad_session_id = await engine.compose(
            component_ids=["does-not-exist"],
            mode=CompositionMode.SEQUENTIAL,
            goal="Should fail"
        )
        bad_session = engine.get_session(bad_session_id)
        print(f"Unknown component compose -> status={bad_session['status']} error={bad_session.get('error')!r}")
        assert bad_session["status"] == "failed"
        assert "not found" in bad_session["error"]

        # Depth-exceeding composition -> real warning, not silently valid
        many_ids = ["map", "filter", "reduce", "analyze", "optimize", "generate"]
        deep_session_id = await engine.compose(
            component_ids=many_ids,
            mode=CompositionMode.SEQUENTIAL,
            goal="Exceed max depth"
        )
        deep_session = engine.get_session(deep_session_id)
        print(f"Deep compose -> warnings={deep_session['validation_result']['warnings']}")
        assert any("exceeds recommended maximum" in w for w in deep_session["validation_result"]["warnings"])

        assert len(engine.list_sessions()) == 4
        assert len(engine.list_composed_algorithms()) == 3  # bad_session never got stored

        print("\nALL ASSERTIONS PASSED")

    asyncio.run(_smoke_test())
