module geometry
  use math_constants
  use system_utils
  implicit none
contains
  subroutine circle_area(r, area)
    real, intent(in) :: r
    real, intent(out) :: area
    area = 3.14159 * r * r
  end subroutine circle_area

  subroutine print_area(area)
    real, intent(in) :: area
    print *, area
  end subroutine print_area

  function distance(x, y) result(d)
    real, intent(in) :: x, y
    real :: d
    d = sqrt(x*x + y*y)
    call print_area(d)
  end function distance
end module geometry

program main
  use geometry
  implicit none
  real :: d
  d = distance(3.0, 4.0)
end program main
