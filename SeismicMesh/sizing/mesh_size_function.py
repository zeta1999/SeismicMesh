# -----------------------------------------------------------------------------
#  Copyright (C) 2020 Keith Jared Roberts

#  Distributed under the terms of the GNU General Public License. You should
#  have received a copy of the license along with this program. If not,
#  see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------
import warnings

import numpy as np
from scipy.interpolate import RegularGridInterpolator
import h5py
import matplotlib.pyplot as plt

import segyio

from ..geometry import signed_distance_functions as sdf
from .cpp import limgrad


class MeshSizeFunction:
    """
    MeshSizeFunction: build an isotropic mesh size function for seismic domains.

    Usage
    -------
    >>> obj = MeshSizeFunction(bbox,hmin,segy,**kwargs)


    Parameters
    -------
        bbox: Bounding box, (xmin, xmax, ymin, ymax)
        hmin: Minimum triangular edgelength populating domain, (meters)
        model: (2D) Seg-y file containing velocity model, (assumes velocity is in METERS PER SECOND)
                                                OR
        (3D) binary file containing velocity model, (assumes velocity is in METERS PER SECOND)
             -Litte endian.
             -Requires to specify number of grid points in each dimension. nx, ny, and nz.

                                **kwargs
        nz: for velocity model, number of grid points in z-direction
        nx: for velocity model, number of grid points in x-direction
        ny: for velocity model, number of grid points in y-direction (only for 3D)
        units: velocity is in either m-s or km-s (default='m-s')
        wl:   number of nodes per wavelength for given max. freq, (num. of nodes per wl., default=disabled)
        freq: maximum source frequency for which to estimate wl (hertz, default=disabled)
        hmax: maximum edgelength in the domain (meters, default=disabled)
        dt: maximum stable timestep (in seconds given Courant number cr, default=disabled)
        cr_max: dt is theoretically stable with this Courant number (default=0.2)
        grade: maximum allowable variation in mesh size (default=disabled)
        domain_ext: width of domain extension (in meters, default=0.0)


    Returns
    -------
        MeshSizeFunction object


    Example (see examples/)
    ------
    import SeismicMesh
    # In 2D
    ef = SeismicMesh.MeshSizeFunction(
            bbox=(-12e3,0,0,67e3),
            ,model=fname,
            hmin=2e3
            # ,wl=5,freq=5
            # ,hmax=4e3
            # ,grade=10.0
            # ,dt=0.001
            # ,cr_max=0.1
            )

    """

    def __init__(
        self,
        bbox,
        hmin,
        model,
        units="m-s",
        wl=0.0,
        freq=5.0,
        hmax=np.inf,
        dt=0.0,
        cr_max=0.2,
        grade=0.0,
        nx=None,
        ny=None,
        nz=None,
        domain_ext=0.0,
        padstyle="edge",
        endianness="little",
    ):
        self.bbox = bbox
        self.dim = int(len(self.bbox) / 2)
        self.width = bbox[3] - bbox[2]
        self.depth = bbox[1] - bbox[0]
        if self.dim == 3:
            self.length = bbox[5] - bbox[4]
        self.spacing = None
        self.model = model
        self.units = units
        self.hmin = hmin
        self.hmax = hmax
        self.wl = wl
        self.freq = freq
        self.dt = dt
        self.cr_max = cr_max
        self.grade = grade
        self.fh = None
        self.fd = None
        self.nx = nx
        self.ny = ny
        self.nz = nz
        self.domain_ext = domain_ext
        self.endianness = endianness
        self.padstyle = padstyle

    ### SETTERS AND GETTERS ###

    @property
    def fh(self):
        return self.__fh

    @fh.setter
    def fh(self, value):
        self.__fh = value

    @property
    def fd(self):
        return self.__fd

    @fd.setter
    def fd(self, value):
        self.__fd = value

    @property
    def bbox(self):
        return self.__bbox

    @bbox.setter
    def bbox(self, value):
        assert (
            len(value) >= 4 and len(value) <= 6
        ), "bbox has wrong number of values. either 4 or 6."
        self.__bbox = value

    @property
    def hmin(self):
        return self.__hmin

    @hmin.setter
    def hmin(self, value):
        assert value > 0.0, "hmin must be non-zero"
        self.__hmin = value

    @property
    def dim(self):
        return self.__dim

    @dim.setter
    def dim(self, value):
        assert value == 2 or value == 3, "dim must be either 2 or 3"
        self.__dim = value

    @property
    def vp(self):
        return self.__vp

    @vp.setter
    def vp(self, value):
        if np.amin(value) < 1000:
            warnings.warn("Min. velocity < 1000 m-s. Units may be incorrect.")
        if np.amax(value) > 10000:
            warnings.warn("Max. velocity > 10,000 m-s. Units may be incorrect.")
        self.__vp = value

    @property
    def nz(self):
        assert self.__nz is not None, "binary file specified but nz was not."
        return self.__nz

    @nz.setter
    def nz(self, value):
        assert value is None or value > 0, " nz is not > 0"
        self.__nz = value

    @property
    def nx(self):
        assert self.__nx is not None, "binary file specified but nx was not."
        return self.__nx

    @nx.setter
    def nx(self, value):
        assert value is None or value > 0, " nx is not > 0"
        self.__nx = value

    @property
    def ny(self):
        assert self.__ny is not None, "binary file specified but ny was not."
        return self.__ny

    @ny.setter
    def ny(self, value):
        assert value is None or value > 0, " ny is not > 0"
        self.__ny = value

    @property
    def model(self):
        return self.__model

    @model.setter
    def model(self, value):
        assert isinstance(value, str) is True, "model must be a filename"
        self.__model = value

    @property
    def units(self):
        return self.__units

    @units.setter
    def units(self, value):
        assert value == "m-s" or value == "km-s", "units are not compatible"
        self.__units = value

    @property
    def wl(self):
        return self.__wl

    @wl.setter
    def wl(self, value):
        self.__wl = value

    @property
    def freq(self):
        return self.__freq

    @freq.setter
    def freq(self, value):
        self.__freq = value

    @property
    def hmax(self):
        return self.__hmax

    @hmax.setter
    def hmax(self, value):
        self.__hmax = value

    @property
    def dt(self):
        return self.__dt

    @dt.setter
    def dt(self, value):
        assert value >= 0, "dt must be > 0"
        self.__dt = value

    @property
    def cr_max(self):
        return self.__cr_max

    @cr_max.setter
    def cr_max(self, value):
        assert value >= 0, "Cr_max must be > 0"
        self.__cr_max = value

    @property
    def grade(self):
        return self.__grade

    @grade.setter
    def grade(self, value):
        assert value >= 0, "grade must be > 0"
        self.__grade = value

    @property
    def domain_ext(self):
        return self.__domain_ext

    @domain_ext.setter
    def domain_ext(self, value):
        assert value >= 0, "domain extent must be > 0"
        self.__domain_ext = value

    @property
    def endianness(self):
        return self.__endianness

    @endianness.setter
    def endianness(self, value):
        assert value == "big" or value == "little", "endianness must be little or big"
        self.__endianness = value

    @property
    def padstyle(self):
        return self.__padstyle

    @padstyle.setter
    def padstyle(self, value):
        assert value == "edge" or value == "constant" or value == "linear_ramp"
        self.__padstyle = value

    # ---PUBLIC METHODS---#

    def build(self):
        """Builds the isotropic mesh size function according
            to the user arguments that were passed.

        Usage
        -------
        >>>> obj = build(self)


        Parameters
        -------
            MeshSizeFunction object

         Returns
        -------
            SeismicMesh.MeshSizeFunction object with specific fields populated:
                self.fh: lambda function w/ scipy.inerpolate.RegularGridInterpolater representing isotropic mesh sizes in domain
                self.fd: lambda function representing the signed distance function of domain

        """
        self.__ReadVelocityModel()
        _vp = self.vp

        _bbox = self.bbox
        _dim = self.dim
        _width = self.width
        _nz = self.nz
        _nx = self.nx
        if _dim == 3:
            _ny = self.ny
        _domain_ext = self.domain_ext

        _hmax = self.hmax
        _hmin = self.hmin
        _grade = self.grade

        _wl = self.wl
        _freq = self.freq

        _dt = self.dt
        _cr_max = self.cr_max

        if _dim == 2:
            hh_m = np.zeros(shape=(_nz, _nx), dtype=np.float32) + _hmin
        if _dim == 3:
            hh_m = np.zeros(shape=(_nz, _nx, _ny), dtype=np.float32) + _hmin
        if _wl > 0:
            print(
                "Mesh sizes will be built to resolve an estimate of wavelength with "
                + str(_wl)
                + " vertices..."
            )
            hh_m = _vp / (_freq * _wl)
        # enforce min (and optionally max) sizes
        hh_m = np.where(hh_m < _hmin, _hmin, hh_m)
        if _hmax < np.inf:
            print("Enforcing maximum mesh resolution...")
            hh_m = np.where(hh_m > _hmax, _hmax, hh_m)
        # grade the mesh sizes
        if _grade > 0:
            print("Enforcing mesh gradation in sizing function...")
            hh_m = self.hj(hh_m, _width / _nx, 10000)
        # adjust mesh res. based on the CFL limit so cr < cr_max
        if _dt > 0:
            print("Enforcing timestep of " + str(_dt) + " seconds...")
            cr_old = (_vp * _dt) / hh_m
            dxn = (_vp * _dt) / _cr_max
            hh_m = np.where(cr_old > _cr_max, dxn, hh_m)
        # edit the bbox to reflect the new domain size
        if _domain_ext > 0:
            self = self.__CreateDomainExtension()
            hh_m = self.__EditMeshSizeFunction(hh_m)
        # construct a interpolator object to be queried during mesh generation
        print("Building a gridded interpolant...")
        if _dim == 2:
            z_vec, x_vec = self.__CreateDomainVectors()
        if _dim == 3:
            z_vec, x_vec, y_vec = self.__CreateDomainVectors()
        assert np.all(hh_m > 0.0), "edge_size_function must be strictly positive."
        if _dim == 2:
            interpolant = RegularGridInterpolator(
                (z_vec, x_vec), hh_m, bounds_error=False, fill_value=None
            )
        if _dim == 3:
            # x,y,z -> z,x,y
            hh_m = hh_m.transpose((2, 0, 1))
            interpolant = RegularGridInterpolator(
                (z_vec, x_vec, y_vec), hh_m, bounds_error=False, fill_value=None
            )
        # create a mesh size function interpolant
        self.fh = lambda p: interpolant(p)

        _bbox = self.bbox

        def fdd(p):
            return sdf.drectangle(p, _bbox[0], _bbox[1], _bbox[2], _bbox[3])

        def fdd2(p):
            return sdf.dblock(
                p, _bbox[0], _bbox[1], _bbox[2], _bbox[3], _bbox[4], _bbox[5]
            )

        # create a signed distance function
        if _dim == 2:
            self.fd = lambda p: fdd(p)
        if _dim == 3:
            self.fd = lambda p: fdd2(p)
        return self

    def plot(self, stride=5):
        """ Plot the isotropic mesh size function

        Usage
        -------
        >>>> plot(self)


        Parameters
        -------
            self: SeismicMesh.MeshSizeFunction object
                        **kwargs
            stride: downsample the image by n (n=5 by default)

         Returns
        -------
            none
            """
        _dim = self.dim
        _fh = self.fh
        _domain_ext = self.domain_ext
        _width = self.width
        _depth = self.depth

        if _dim == 2:
            zg, xg = self.__CreateDomainMatrices()
            sz1z, sz1x = zg.shape
            _zg = np.reshape(zg, (-1, 1))
            _xg = np.reshape(xg, (-1, 1))
            hh = _fh((_zg, _xg))
            hh = np.reshape(hh, (sz1z, sz1x))

            fig, ax = plt.subplots()
            plt.pcolormesh(
                xg[0::stride], zg[0::stride], hh[0::stride], edgecolors="none"
            )
            if _domain_ext > 0:
                rect = plt.Rectangle(
                    (0, -_depth + _domain_ext),
                    _width - 2 * _domain_ext,
                    _depth - _domain_ext,
                    fill=False,
                    edgecolor="black",
                )
                ax.add_patch(rect)

            plt.title("Isotropic mesh sizes")
            plt.colorbar(label="mesh size (m)")
            plt.xlabel("x-direction (km)")
            plt.ylabel("z-direction (km)")
            ax.axis("equal")
            # ax.set_xlim(0 - _domain_ext, _width)
            # ax.set_ylim(-_depth, 0)
            plt.show()
        elif _dim == 3:
            print("visualization in 3D not yet supported!")
        return None

    def GetDomainMatrices(self):
        """ Accessor to private method"""
        zg, xg = self.__CreateDomainMatrices()
        return zg, xg

    def hj(self, fun, elen, imax):
        """ Call-back to the cpp gradient limiter code """
        _dim = self.dim
        _nz = self.nz
        _nx = self.nx
        if _dim == 3:
            _ny = self.ny
        _grade = self.grade

        ffun = fun.flatten("F")
        ffun_list = ffun.tolist()
        if _dim == 2:
            tmp = limgrad([_nz, _nx, 1], elen, _grade, imax, ffun_list)
        if _dim == 3:
            tmp = limgrad([_nx, _ny, _nz], elen, _grade, imax, ffun_list)
        tmp = np.asarray(tmp)
        if _dim == 2:
            fun_s = np.reshape(tmp, (_nz, _nx), "F")
        if _dim == 3:
            fun_s = np.reshape(tmp, (_nx, _ny, _nz), "F")
        return fun_s

    def WriteVelocityModel(self, ofname):
        """ Writes a velocity model as a hdf5 file for use in Spyro """
        _dim = self.dim
        _vp = self.vp
        _nz = self.nz
        _nx = self.nx
        _domain_ext = self.domain_ext
        _spacing = self.spacing
        _padstyle = self.padstyle
        nnx = int(_domain_ext / _spacing)
        # create domain extension in velocity model
        if _dim == 2:
            mx = np.amax(_vp)
            if _padstyle == "edge":
                _vp = np.pad(_vp, ((nnx, 0), (nnx, nnx)), "edge")
            elif _padstyle == "constant":
                # set to maximum value in domain
                _vp = np.pad(
                    _vp, ((nnx, 0), (nnx, nnx)), "constant", constant_values=(mx, mx)
                )
            elif _padstyle == "linear_ramp":
                # linearly ramp to maximum value in domain
                _vp = np.pad(
                    _vp, ((nnx, 0), (nnx, nnx)), "linear_ramp", end_values=(mx, mx)
                )
        if _dim == 3:
            _vp = np.pad(_vp, ((nnx, nnx), (nnx, nnx), (nnx, 0)), "edge")

        _nz += nnx  # only bottom
        _nx += nnx * 2  # left and right
        if _dim == 3:
            _ny = self.ny
            _ny += nnx * 2  # behind and in front

        model_fname = self.model
        ofname += ".hdf5"
        print("Writing velocity model " + ofname)
        with h5py.File(ofname, "w") as f:
            f.create_dataset("velocity_model", data=_vp, dtype="f")
            if _dim == 2:
                f.attrs["shape"] = (_nz, _nx)
            elif _dim == 3:
                f.attrs["shape"] = (_nz, _nx, _ny)
            f.attrs["units"] = "m/s"
            f.attrs["source"] = model_fname

    def SaveMeshSizeFunctionOptions(self, ofname):
        " Save your mesh size function options as a hdf5 file" ""
        ofname += ".hdf5"
        print("Saving mesh size function options " + ofname)
        with h5py.File(ofname, "a") as f:
            f.attrs["bbox"] = self.bbox
            f.attrs["model"] = self.model
            f.attrs["units"] = self.units
            f.attrs["hmin"] = self.hmin
            f.attrs["hmax"] = self.hmax
            f.attrs["wl"] = self.wl
            f.attrs["freq"] = self.freq
            f.attrs["dt"] = self.dt
            f.attrs["cr_max"] = self.cr_max
            f.attrs["grade"] = self.grade
            f.attrs["nx"] = self.nx
            if self.dim == 3:
                f.attrs["ny"] = self.ny
            f.attrs["nz"] = self.nz
            f.attrs["domain_ext"] = self.domain_ext
            f.attrs["padstyle"] = self.padstyle

    # ---PRIVATE METHODS---#

    def __ReadVelocityModel(self):
        """ Reads a velocity model from a SEG-Y file (2D) or a binary file (3D). Uses the python package segyio."""
        _fname = self.model
        # determine type of file
        isSegy = _fname.lower().endswith((".segy"))
        isBin = _fname.lower().endswith((".bin"))
        if isSegy:
            print("Found SEG-Y file: " + _fname)
            with segyio.open(_fname, ignore_geometry=True) as f:
                # determine dimensions of velocity model from trace length
                self.nz = len(f.samples)
                self.nx = len(f.trace)
                _nz = self.nz
                _nx = self.nx
                self.spacing = self.width / _nx
                _vp = np.zeros(shape=(_nz, _nx))
                index = 0
                for trace in f.trace:
                    _vp[:, index] = trace
                    index += 1
                _vp = np.flipud(_vp)
        elif isBin:
            print("Found binary file: " + _fname)
            _nx = self.nx
            _ny = self.ny
            _nz = self.nz
            self.spacing = self.width / _nx
            _type = self.endianness
            # assumes file is little endian byte order and fortran ordering (column-wise)
            with open(_fname, "r") as file:
                _vp = np.fromfile(file, dtype=np.dtype("float32").newbyteorder(">"))
                _vp = _vp.reshape(_nx, _ny, _nz, order="F")
            # if file was big endian then switch to little endian
            if _type == "big":
                _vp = _vp.byteswap()
        else:
            print("Did not recognize file type...either .bin or .segy")
            quit()
        if self.__units == "km-s":
            print("Converting model velocities to m-s...")
            _vp *= 1e3
        self.vp = _vp
        return None

    def __CreateDomainVectors(self):
        _dim = self.dim
        _nz = self.nz
        _nx = self.nx
        if _dim == 3:
            _ny = self.ny
            _len = self.length
        _width = self.width
        _depth = self.depth
        _domain_ext = self.domain_ext
        _spacing = self.spacing

        # if domain extension is enabled, we augment the domain vectors
        nnx = int(_domain_ext / _spacing)
        if _domain_ext > 0:
            _nz += nnx  # only bottom
            _nx += nnx * 2  # left and right
            if _dim == 3:
                _ny += nnx * 2  # behind and in front

        zvec = np.linspace(-_depth, 0, _nz, dtype=np.float32)
        xvec = np.linspace(0 - _domain_ext, _width - _domain_ext, _nx, dtype=np.float32)

        if _dim == 2:
            return zvec, xvec
        elif _dim == 3:
            yvec = np.linspace(
                0 - _domain_ext, _len - _domain_ext, _ny, dtype=np.float32
            )
            return zvec, xvec, yvec

    def __CreateDomainMatrices(self):
        _dim = self.dim
        if _dim == 2:
            zvec, xvec = self.__CreateDomainVectors()
            zg, xg = np.meshgrid(zvec, xvec, indexing="ij")
            return zg, xg
        elif _dim == 3:
            zvec, xvec, yvec = self.__CreateDomainVectors()
            xg, yg, zg = np.meshgrid(
                xvec, yvec, zvec, indexing="ij", sparse=True, copy=False
            )
            return zg, xg, yg

    def __EditMeshSizeFunction(self, hh_m):
        """ Edits sizing function to support domain extension of variable width """
        _domain_ext = self.domain_ext
        _dim = self.dim
        _hmax = self.hmax
        _spacing = self.spacing
        _padstyle = self.padstyle

        nnx = int(_domain_ext / _spacing)

        print("Including a " + str(_domain_ext) + " meter domain extension...")
        print("Using the padstyle " + _padstyle + " to extend mesh resolution.")
        if _dim == 2:
            mx = np.amax(hh_m)
            if _padstyle == "edge":
                hh_m = np.pad(hh_m, ((nnx, 0), (nnx, nnx)), "edge")
            elif _padstyle == "constant":
                # set to maximum value in domain
                hh_m = np.pad(
                    hh_m, ((nnx, 0), (nnx, nnx)), "constant", constant_values=(mx, mx)
                )
            elif _padstyle == "linear_ramp":
                # linearly ramp to maximum value in domain
                hh_m = np.pad(
                    hh_m, ((nnx, 0), (nnx, nnx)), "linear_ramp", end_values=(mx, mx)
                )
            hh_m = np.where(hh_m > _hmax, _hmax, hh_m)
            return hh_m
        if _dim == 3:
            if _padstyle == "edge":
                hh_m = np.pad(hh_m, ((nnx, nnx), (nnx, nnx), (nnx, 0)), "edge")
            else:
                print("3D pad style currently not supported yet")
            hh_m = np.where(hh_m > _hmax, _hmax, hh_m)
            return hh_m

    def __CreateDomainExtension(self):
        """ edit bbox to reflect domain extension (should be a function) """
        _dim = self.dim
        _bbox = self.bbox
        _domain_ext = self.domain_ext
        if _domain_ext > 0:
            if _dim == 2:
                bbox_new = (
                    _bbox[0] - _domain_ext,
                    _bbox[1],
                    _bbox[2] - _domain_ext,
                    _bbox[3] + _domain_ext,
                )
            if _dim == 3:
                bbox_new = (
                    _bbox[0] - _domain_ext,
                    _bbox[1],
                    _bbox[2] - _domain_ext,
                    _bbox[3] + _domain_ext,
                    _bbox[4] - _domain_ext,
                    _bbox[5] + _domain_ext,
                )

            self.bbox = bbox_new
            self.width = bbox_new[3] - bbox_new[2]
            self.depth = bbox_new[1] - bbox_new[0]
            if _dim == 3:
                self.length = bbox_new[5] - bbox_new[4]
        return self