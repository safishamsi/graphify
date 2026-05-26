// ──────────────────────────────────────────────────────────────────────────
// Kitchen-sink ReScript fixture. Every documented extractor surface is
// exercised at least once: each type form, each let shape, each external
// shape, nested modules, every call dispatch path, and every context that
// emits a `references_type` edge.
//
// Cross-module references (Animal.point, Belt.Array.get, etc.) are
// intentional — they verify that the per-file cleanup keeps
// `references_type` edges with phantom targets (the multi-file resolver
// in `extract()` is exercised by separate `tmp_path` tests).
// ──────────────────────────────────────────────────────────────────────────

// ── Type forms ────────────────────────────────────────────────────────────

type theme = [
  | #Light
  | #Dark
  | #Auto
]

type direction =
  | North
  | South
  | East
  | West

type label = string

type entry = {
  name: string,
  position: Animal.point,
}

// ── External declarations ────────────────────────────────────────────────

external alert: string => unit = "alert"
external pi: float = "Math.PI"

// ── Value lets ───────────────────────────────────────────────────────────

let allThemes = [#Light, #Dark, #Auto]

let origin = {name: "origin", position: Animal.zero}

let (width, height) = (1024, 768)

let {name, position} = origin

let defaultEntry: Animal.point = Animal.zero

// ── Function lets ────────────────────────────────────────────────────────

let identity = (x) => x

let move = (a: Animal.point, dx: int, dy: int): Animal.point =>
  Animal.shift(a, dx, dy)

let pair = (a, b) => identity(b)

let firstTheme = () => Belt.Array.get(allThemes, 0)

let counts = (xs) =>
  xs->Belt.Array.map(identity)

// ── Module with nested type, value, and function ────────────────────────

module Internal = {
  type cached = {
    value: int,
    species: Animal.species,
  }

  let defaultCache = 0

  let parse = (json) => Json.decode(json)
}
