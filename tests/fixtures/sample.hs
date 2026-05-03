module Sample where

import Data.List
import qualified Data.Map as Map

-- Algebraic data type with constructors
data Shape
  = Circle Double
  | Rectangle Double Double

-- Newtype wrapper
newtype Wrapper a = Wrapper a

-- Type alias
type Name = String

-- Type class
class Describable a where
  describe :: a -> String

-- Instance
instance Describable Shape where
  describe (Circle r) = "Circle with radius " ++ show r
  describe (Rectangle w h) = "Rectangle " ++ show w ++ "x" ++ show h

-- Function with type signature
area :: Shape -> Double
area (Circle r) = pi * r * r
area (Rectangle w h) = w * h

-- Function that calls other functions
perimeter :: Shape -> Double
perimeter (Circle r) = 2.0 * pi * r
perimeter (Rectangle w h) = 2.0 * (w + h)

-- Function using guards
classify :: Shape -> String
classify shape
  | a > 100   = "large"
  | a > 10    = "medium"
  | otherwise = "small"
  where
    a = area shape

-- Function calling multiple others
summarize :: Shape -> String
summarize shape = describe shape ++ " area=" ++ show (area shape)

-- Simple helper
double :: Double -> Double
double x = x * 2
