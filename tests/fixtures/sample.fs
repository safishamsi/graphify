open System.Collections.Generic

type Color =
    | Red
    | Green
    | Blue

type Point = { X: float; Y: float }

type Distance = float

module Geometry =
    let origin = { X = 0.0; Y = 0.0 }

    let distance (a: Point) (b: Point) =
        let dx = a.X - b.X
        let dy = a.Y - b.Y
        sqrt (dx * dx + dy * dy)

    let midpoint (a: Point) (b: Point) =
        { X = (a.X + b.X) / 2.0; Y = (a.Y + b.Y) / 2.0 }

let colorName color =
    match color with
    | Red -> "red"
    | Green -> "green"
    | Blue -> "blue"

let describePoint (p: Point) =
    let d = Geometry.distance p Geometry.origin
    sprintf "(%f, %f) at distance %f" p.X p.Y d

let processPoints (points: Point list) =
    points
    |> List.map describePoint
    |> List.filter (fun s -> s.Length > 0)
