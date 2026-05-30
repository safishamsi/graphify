module geometry
  use constants
  implicit none

  real, parameter :: PI = 3.14159

  type :: Point
    real :: x
    real :: y
  end type Point

contains

  subroutine circle_area(radius, area)
    real, intent(in) :: radius
    real, intent(out) :: area
    area = PI * radius * radius
  end subroutine circle_area

  function distance(x1, y1, x2, y2) result(d)
    real, intent(in) :: x1, y1, x2, y2
    real :: d
    d = sqrt((x2 - x1)**2 + (y2 - y1)**2)
  end function distance

  subroutine translate(p, dx, dy)
    type(Point), intent(inout) :: p
    real, intent(in) :: dx, dy
    p%x = p%x + dx
    p%y = p%y + dy
  end subroutine translate

  function origin() result(p)
    type(Point) :: p
    p%x = 0.0
    p%y = 0.0
  end function origin

  subroutine print_area(radius)
    real, intent(in) :: radius
    real :: area
    call circle_area(radius, area)
    print *, "Area =", area
  end subroutine print_area

end module geometry


program main
  use geometry
  implicit none

  real :: r, a
  r = 5.0
  call circle_area(r, a)
  print *, "Circle area:", a
end program main
