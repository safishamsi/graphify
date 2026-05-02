#define NDIM 3

module shapes
#ifdef MPI
  use mpi
#endif
  implicit none

contains

  subroutine compute_volume(side, vol)
    real, intent(in) :: side
    real, intent(out) :: vol
    vol = side ** NDIM
  end subroutine compute_volume

end module shapes
