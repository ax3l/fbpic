# Copyright 2016, FBPIC contributors
# Authors: Remi Lehe, Manuel Kirchen, Kevin Peters
# License: 3-Clause-BSD-LBNL
"""
This file is part of the Fourier-Bessel Particle-In-Cell code (FB-PIC)
It defines the field gathering methods linear and cubic order shapes
on the GPU using CUDA.
"""
from numba import cuda, float64, int64
import math
# Import inline functions
from .inline_functions import \
    add_linear_gather_for_mode, add_cubic_gather_for_mode
# Compile the inline functions for GPU
add_linear_gather_for_mode = cuda.jit( add_linear_gather_for_mode,
                                        device=True, inline=True )
add_cubic_gather_for_mode = cuda.jit( add_cubic_gather_for_mode,
                                        device=True, inline=True )

# -----------------------
# Field gathering linear
# -----------------------

@cuda.jit
def gather_field_gpu_linear(x, y, z,
                    invdz, zmin, Nz,
                    invdr, rmin, Nr,
                    Er_m0, Et_m0, Ez_m0,
                    Er_m1, Et_m1, Ez_m1,
                    Br_m0, Bt_m0, Bz_m0,
                    Br_m1, Bt_m1, Bz_m1,
                    Ex, Ey, Ez,
                    Bx, By, Bz):
    """
    Gathering of the fields (E and B) using numba on the GPU.
    Iterates over the particles, calculates the weighted amount
    of fields acting on each particle based on its shape (linear).
    Fields are gathered in cylindrical coordinates and then
    transformed to cartesian coordinates.
    Supports only mode 0 and 1.

    Parameters
    ----------
    x, y, z : 1darray of floats (in meters)
        The position of the particles

    invdz, invdr : float (in meters^-1)
        Inverse of the grid step along the considered direction

    zmin, rmin : float (in meters)
        Position of the edge of the simulation box along the
        direction considered

    Nz, Nr : int
        Number of gridpoints along the considered direction

    Er_m0, Et_m0, Ez_m0 : 2darray of complexs
        The electric fields on the interpolation grid for the mode 0

    Er_m1, Et_m1, Ez_m1 : 2darray of complexs
        The electric fields on the interpolation grid for the mode 1

    Br_m0, Bt_m0, Bz_m0 : 2darray of complexs
        The magnetic fields on the interpolation grid for the mode 0

    Br_m1, Bt_m1, Bz_m1 : 2darray of complexs
        The magnetic fields on the interpolation grid for the mode 1

    Ex, Ey, Ez : 1darray of floats
        The electric fields acting on the particles
        (is modified by this function)

    Bx, By, Bz : 1darray of floats
        The magnetic fields acting on the particles
        (is modified by this function)
    """
    # Get the 1D CUDA grid
    i = cuda.grid(1)
    # Deposit the field per cell in parallel
    # (for threads < number of particles)
    if i < x.shape[0]:
        # Preliminary arrays for the cylindrical conversion
        # --------------------------------------------
        # Position
        xj = x[i]
        yj = y[i]
        zj = z[i]

        # Cylindrical conversion
        rj = math.sqrt( xj**2 + yj**2 )
        if (rj !=0. ) :
            invr = 1./rj
            cos = xj*invr  # Cosine
            sin = yj*invr  # Sine
        else :
            cos = 1.
            sin = 0.
        exptheta_m0 = 1.
        exptheta_m1 = cos - 1.j*sin

        # Get linear weights for the deposition
        # --------------------------------------------
        # Positions of the particles, in the cell unit
        r_cell =  invdr*(rj - rmin) - 0.5
        z_cell =  invdz*(zj - zmin) - 0.5
        # Original index of the uppper and lower cell
        ir_lower = int(math.floor( r_cell ))
        ir_upper = ir_lower + 1
        iz_lower = int(math.floor( z_cell ))
        iz_upper = iz_lower + 1
        # Linear weight
        Sr_lower = ir_upper - r_cell
        Sr_upper = r_cell - ir_lower
        Sz_lower = iz_upper - z_cell
        Sz_upper = z_cell - iz_lower
        # Set guard weights to zero
        Sr_guard = 0.

        # Treat the boundary conditions
        # --------------------------------------------
        # guard cells in lower r
        if ir_lower < 0:
            Sr_guard = Sr_lower
            Sr_lower = 0.
            ir_lower = 0
        # absorbing in upper r
        if ir_lower > Nr-1:
            ir_lower = Nr-1
        if ir_upper > Nr-1:
            ir_upper = Nr-1
        # periodic boundaries in z
        # lower z boundaries
        if iz_lower < 0:
            iz_lower += Nz
        if iz_upper < 0:
            iz_upper += Nz
        # upper z boundaries
        if iz_lower > Nz-1:
            iz_lower -= Nz
        if iz_upper > Nz-1:
            iz_upper -= Nz

        # Precalculate Shapes
        S_ll = Sz_lower*Sr_lower
        S_lu = Sz_lower*Sr_upper
        S_ul = Sz_upper*Sr_lower
        S_uu = Sz_upper*Sr_upper
        S_lg = Sz_lower*Sr_guard
        S_ug = Sz_upper*Sr_guard

        # E-Field
        # -------
        Fr = 0.
        Ft = 0.
        Fz = 0.
        # Add contribution from mode 0
        Fr, Ft, Fz = add_linear_gather_for_mode( 0,
            Fr, Ft, Fz, exptheta_m0, Er_m0, Et_m0, Ez_m0,
            iz_lower, iz_upper, ir_lower, ir_upper,
            S_ll, S_lu, S_lg, S_ul, S_uu, S_ug )
        # Add contribution from mode 1
        Fr, Ft, Fz = add_linear_gather_for_mode( 1,
            Fr, Ft, Fz, exptheta_m1, Er_m1, Et_m1, Ez_m1,
            iz_lower, iz_upper, ir_lower, ir_upper,
            S_ll, S_lu, S_lg, S_ul, S_uu, S_ug )
        # Convert to Cartesian coordinates
        # and write to particle field arrays
        Ex[i] = cos*Fr - sin*Ft
        Ey[i] = sin*Fr + cos*Ft
        Ez[i] = Fz

        # B-Field
        # -------
        # Clear the placeholders for the
        # gathered field for each coordinate
        Fr = 0.
        Ft = 0.
        Fz = 0.
        # Add contribution from mode 0
        Fr, Ft, Fz = add_linear_gather_for_mode( 0,
            Fr, Ft, Fz, exptheta_m0, Br_m0, Bt_m0, Bz_m0,
            iz_lower, iz_upper, ir_lower, ir_upper,
            S_ll, S_lu, S_lg, S_ul, S_uu, S_ug )
        # Add contribution from mode 1
        Fr, Ft, Fz = add_linear_gather_for_mode( 1,
            Fr, Ft, Fz, exptheta_m1, Br_m1, Bt_m1, Bz_m1,
            iz_lower, iz_upper, ir_lower, ir_upper,
            S_ll, S_lu, S_lg, S_ul, S_uu, S_ug )
        # Convert to Cartesian coordinates
        # and write to particle field arrays
        Bx[i] = cos*Fr - sin*Ft
        By[i] = sin*Fr + cos*Ft
        Bz[i] = Fz

# -----------------------
# Field gathering cubic
# -----------------------

@cuda.jit
def gather_field_gpu_cubic(x, y, z,
                    invdz, zmin, Nz,
                    invdr, rmin, Nr,
                    Er_m0, Et_m0, Ez_m0,
                    Er_m1, Et_m1, Ez_m1,
                    Br_m0, Bt_m0, Bz_m0,
                    Br_m1, Bt_m1, Bz_m1,
                    Ex, Ey, Ez,
                    Bx, By, Bz):
    """
    Gathering of the fields (E and B) using numba on the GPU.
    Iterates over the particles, calculates the weighted amount
    of fields acting on each particle based on its shape (cubic).
    Fields are gathered in cylindrical coordinates and then
    transformed to cartesian coordinates.
    Supports only mode 0 and 1.

    Parameters
    ----------
    x, y, z : 1darray of floats (in meters)
        The position of the particles

    invdz, invdr : float (in meters^-1)
        Inverse of the grid step along the considered direction

    zmin, rmin : float (in meters)
        Position of the edge of the simulation box along the
        direction considered

    Nz, Nr : int
        Number of gridpoints along the considered direction

    Er_m0, Et_m0, Ez_m0 : 2darray of complexs
        The electric fields on the interpolation grid for the mode 0

    Er_m1, Et_m1, Ez_m1 : 2darray of complexs
        The electric fields on the interpolation grid for the mode 1

    Br_m0, Bt_m0, Bz_m0 : 2darray of complexs
        The magnetic fields on the interpolation grid for the mode 0

    Br_m1, Bt_m1, Bz_m1 : 2darray of complexs
        The magnetic fields on the interpolation grid for the mode 1

    Ex, Ey, Ez : 1darray of floats
        The electric fields acting on the particles
        (is modified by this function)

    Bx, By, Bz : 1darray of floats
        The magnetic fields acting on the particles
        (is modified by this function)
    """

    # Get the 1D CUDA grid
    i = cuda.grid(1)
    # Deposit the field per cell in parallel
    # (for threads < number of particles)
    if i < x.shape[0]:
        # Preliminary arrays for the cylindrical conversion
        # --------------------------------------------
        # Position
        xj = x[i]
        yj = y[i]
        zj = z[i]

        # Cylindrical conversion
        rj = math.sqrt(xj**2 + yj**2)
        if (rj != 0.):
            invr = 1./rj
            cos = xj*invr  # Cosine
            sin = yj*invr  # Sine
        else:
            cos = 1.
            sin = 0.
        exptheta_m0 = 1.
        exptheta_m1 = cos - 1.j*sin

        # Get weights for the deposition
        # --------------------------------------------
        # Positions of the particle, in the cell unit
        r_cell = invdr*(rj - rmin) - 0.5
        z_cell = invdz*(zj - zmin) - 0.5

        # Calculate the shape factors
        ir = cuda.local.array((4,), dtype=int64)
        Sr = cuda.local.array((4,), dtype=float64)
        ir[0] = int64(math.floor(r_cell)) - 1
        ir[1] = ir[0] + 1
        ir[2] = ir[1] + 1
        ir[3] = ir[2] + 1
        Sr[0] = -1./6. * ((r_cell-ir[0])-2)**3
        Sr[1] = 1./6. * (3*((r_cell-ir[1])**3)-6*((r_cell-ir[1])**2)+4)
        Sr[2] = 1./6. * (3*((ir[2]-r_cell)**3)-6*((ir[2]-r_cell)**2)+4)
        Sr[3] = -1./6. * ((ir[3]-r_cell)-2)**3
        iz = cuda.local.array((4,), dtype=int64)
        Sz = cuda.local.array((4,), dtype=float64)
        iz[0] = int64(math.floor(z_cell)) - 1
        iz[1] = iz[0] + 1
        iz[2] = iz[1] + 1
        iz[3] = iz[2] + 1
        Sz[0] = -1./6. * ((z_cell-iz[0])-2)**3
        Sz[1] = 1./6. * (3*((z_cell-iz[1])**3)-6*((z_cell-iz[1])**2)+4)
        Sz[2] = 1./6. * (3*((iz[2]-z_cell)**3)-6*((iz[2]-z_cell)**2)+4)
        Sz[3] = -1./6. * ((iz[3]-z_cell)-2)**3
        # Lower and upper periodic boundary for z
        for index_z in range(4):
            if iz[index_z] < 0:
                iz[index_z] += Nz
            if iz[index_z] > Nz - 1:
                iz[index_z] -= Nz
        # Lower and upper boundary for r
        for index_r in range(4):
            if ir[index_r] < 0:
                ir[index_r] = abs(ir[index_r])-1
                Sr[index_r] = (-1.)*Sr[index_r]
            if ir[index_r] > Nr - 1:
                ir[index_r] = Nr - 1

        # E-Field
        # -------
        Fr = 0.
        Ft = 0.
        Fz = 0.
        # Add contribution from mode 0
        Fr, Ft, Fz = add_cubic_gather_for_mode( 0,
            Fr, Ft, Fz, exptheta_m0, Er_m0, Et_m0, Ez_m0,
            ir, iz, Sr, Sz )
        # Add contribution from mode 1
        Fr, Ft, Fz = add_cubic_gather_for_mode( 1,
            Fr, Ft, Fz, exptheta_m1, Er_m1, Et_m1, Ez_m1,
            ir, iz, Sr, Sz )
        # Convert to Cartesian coordinates
        # and write to particle field arrays
        Ex[i] = cos*Fr - sin*Ft
        Ey[i] = sin*Fr + cos*Ft
        Ez[i] = Fz

        # B-Field
        # -------
        # Clear the placeholders for the
        # gathered field for each coordinate
        Fr = 0.
        Ft = 0.
        Fz = 0.
        # Add contribution from mode 0
        Fr, Ft, Fz =  add_cubic_gather_for_mode( 0,
            Fr, Ft, Fz, exptheta_m0, Br_m0, Bt_m0, Bz_m0,
            ir, iz, Sr, Sz )
        # Add contribution from mode 1
        Fr, Ft, Fz =  add_cubic_gather_for_mode( 1,
            Fr, Ft, Fz, exptheta_m1, Br_m1, Bt_m1, Bz_m1,
            ir, iz, Sr, Sz )
        # Convert to Cartesian coordinates
        # and write to particle field arrays
        Bx[i] = cos*Fr - sin*Ft
        By[i] = sin*Fr + cos*Ft
        Bz[i] = Fz
